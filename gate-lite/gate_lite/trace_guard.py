"""PEB-23-style property-based trace guard for agent execution traces.

Evaluates deterministic cybernetic invariants over a step stream and, on
violation, shrinks the trace to a minimal failing counterexample sealed by a
SHA-256 replay digest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

CLAIM_KINDS = {"claim", "claim_complete", "assert", "complete", "finish", "done"}
WRITE_KINDS = {"write", "file_write", "edit", "exec", "action", "tool_call"}
FAIL_STATUSES = {"error", "failed", "failure", "denied", "timeout"}


@dataclass(frozen=True)
class Step:
    index: int
    kind: str
    target: str | None
    ok: bool
    scope: str | None
    evidence: str | None
    tokens: int
    pending_gates: tuple[str, ...]
    raw: dict[str, Any]


def _first(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in raw and raw[key] is not None:
            return raw[key]
    return None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off", "error", "failed"}
    return bool(value)


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def normalize_step(raw: dict[str, Any], index: int) -> Step:
    kind = str(_first(raw, "type", "kind", "event", "action") or "step").lower()
    status = str(_first(raw, "status", "result") or "").lower()
    if "ok" in raw:
        ok = _as_bool(raw["ok"])
    elif "success" in raw:
        ok = _as_bool(raw["success"])
    elif status:
        ok = status not in FAIL_STATUSES and status not in {"fail"}
    else:
        ok = True
    gates = _first(raw, "pending_gates", "artifact_gates", "unverified_gates") or ()
    if isinstance(gates, str):
        gates = (gates,)
    return Step(
        index=index,
        kind=kind,
        target=(
            _first(raw, "target", "tool", "path", "file", "id", "name")
        ),
        ok=ok,
        scope=_first(raw, "scope", "allowed_scope"),
        evidence=_first(raw, "evidence_sha256", "evidence", "digest", "proof"),
        tokens=_as_int(_first(raw, "tokens", "cost_tokens", "compute")),
        pending_gates=tuple(str(g) for g in gates),
        raw=raw,
    )


def normalize_steps(raw_steps: Iterable[dict[str, Any]]) -> list[Step]:
    return [normalize_step(dict(raw), i) for i, raw in enumerate(raw_steps)]


def evaluate(
    steps: Sequence[Step],
    allowed_scopes: Sequence[str] | None = None,
    budget_tokens: int | None = None,
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    allowed = set(allowed_scopes or ())
    spent = 0
    fail_target: str | None = None
    fail_streak = 0

    for step in steps:
        if step.kind in WRITE_KINDS or _as_bool(step.raw.get("out_of_scope")):
            if _as_bool(step.raw.get("out_of_scope")):
                violations.append({
                    "property": "ScopeConfinement",
                    "step": step.index,
                    "detail": "step marked out_of_scope",
                })
            elif allowed and step.scope is not None and step.scope not in allowed:
                violations.append({
                    "property": "ScopeConfinement",
                    "step": step.index,
                    "detail": f"scope {step.scope!r} not in {sorted(allowed)!r}",
                })

        if step.ok:
            fail_target = None
            fail_streak = 0
        else:
            if step.target is not None and step.target == fail_target:
                fail_streak += 1
            else:
                fail_target = step.target
                fail_streak = 1
            if fail_streak >= 3:
                violations.append({
                    "property": "AntiThrashLoop",
                    "step": step.index,
                    "detail": f"{fail_streak} consecutive failures on {step.target!r}",
                })

        if step.kind in CLAIM_KINDS:
            if step.pending_gates:
                violations.append({
                    "property": "ContextAnxietyGuard",
                    "step": step.index,
                    "detail": f"completion claimed with pending gates {list(step.pending_gates)!r}",
                })
            if not step.evidence:
                violations.append({
                    "property": "EvidenceBeforeClaim",
                    "step": step.index,
                    "detail": "claim/complete step lacks evidence digest",
                })

        spent += step.tokens
        if budget_tokens is not None and spent > budget_tokens:
            violations.append({
                "property": "BudgetMonotonicity",
                "step": step.index,
                "detail": f"cumulative tokens {spent} exceed budget {budget_tokens}",
            })
            budget_tokens = None

    return violations


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def shrink(
    items: Sequence[Step],
    predicate: Callable[[Sequence[Step]], bool],
) -> list[Step]:
    """Greedy ddmin-style chunk removal; returns a minimal failing subsequence."""
    current = list(items)
    if len(current) <= 2:
        return current
    chunk = max(1, len(current) // 2)
    while chunk >= 1:
        i = 0
        reduced = False
        while i < len(current):
            candidate = current[:i] + current[i + chunk:]
            if candidate and predicate(candidate):
                current = candidate
                reduced = True
            else:
                i += chunk
        if not reduced:
            if chunk == 1:
                break
            chunk //= 2
    return current


def guard_trace(
    raw_steps: Iterable[dict[str, Any]],
    allowed_scopes: Sequence[str] | None = None,
    budget_tokens: int | None = None,
) -> dict[str, Any]:
    steps = normalize_steps(raw_steps)
    violations = evaluate(steps, allowed_scopes=allowed_scopes, budget_tokens=budget_tokens)
    result: dict[str, Any] = {
        "ok": not violations,
        "violations": violations,
        "original_len": len(steps),
        "shrunk_len": 0,
        "compression": None,
        "replay_sha256": None,
    }
    if not violations:
        return result

    shrunk = shrink(
        steps,
        lambda candidate: bool(evaluate(candidate, allowed_scopes=allowed_scopes, budget_tokens=budget_tokens)),
    )
    replay = _canonical([step.raw for step in shrunk])
    result.update({
        "shrunk_len": len(shrunk),
        "compression": round(len(steps) / max(len(shrunk), 1), 2) if steps else None,
        "replay_sha256": hashlib.sha256(replay).hexdigest(),
        "shrunk": [step.raw for step in shrunk],
    })
    return result


def _load_steps(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("steps", data.get("trace", []))
    if not isinstance(data, list):
        raise ValueError("trace file must be a JSON list or an object with 'steps'")
    return data


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate and shrink an agent execution trace.")
    parser.add_argument("trace", type=Path, help="JSON trace file (list or {\"steps\": [...]})")
    parser.add_argument("--allowed-scope", action="append", dest="allowed_scopes", default=None)
    parser.add_argument("--budget-tokens", type=int, default=None)
    parser.add_argument("--json", action="store_true", help="emit full JSON result")
    args = parser.parse_args(argv)

    try:
        steps = _load_steps(args.trace)
        result = guard_trace(steps, allowed_scopes=args.allowed_scopes, budget_tokens=args.budget_tokens)
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        status = "PASS" if result["ok"] else "FAIL"
        print(f"trace guard: {status} ({result['original_len']} steps)")
        for violation in result["violations"]:
            print(f"  - {violation['property']} @ step[{violation['step']}]: {violation['detail']}")
        if result["shrunk_len"]:
            print(
                f"  shrunk {result['original_len']} -> {result['shrunk_len']} steps "
                f"({result['compression']}x) replay={result['replay_sha256']}"
            )
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
