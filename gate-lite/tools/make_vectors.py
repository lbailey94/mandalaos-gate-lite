#!/usr/bin/env python3
"""Generate gate-lite Continuity Receipt vectors for an explicitly selected spec."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from continuity_receipt import keys, records  # noqa: E402
from continuity_receipt.bundle import TaskChain, receipt_digest  # noqa: E402
from continuity_receipt.canon import commit_field, sha256_prefixed  # noqa: E402

VECTORS = ROOT / "vectors"
SPECS = ("continuity-receipt/0.4", "continuity-receipt/0.5")
SPEC_ALIASES = {spec.rsplit("/", 1)[1]: spec for spec in SPECS}
POLICY = "2026-09-17.1"

GATE_DID, GATE_KEY = keys.generate(keys.deterministic_seed("gate-1"))
AGENT_DID, AGENT_KEY = keys.generate(keys.deterministic_seed("agent-1"))
COUNTERPARTY_DID, _COUNTERPARTY_KEY = keys.generate(keys.deterministic_seed("counterparty-1"))


def digest(label: str) -> str:
    return sha256_prefixed(label.encode())


def pass_body(spend_cap=None) -> dict:
    body = {
        "gate_id": "gate-lite-1",
        "mandala_class": "gate-lite",
        "quotas": {"cpu_ms": 300000, "mem_mb": 1024, "disk_mb": 512, "wall_ms": 300000},
        "expires_at": "2026-09-18T00:00:00Z",
        "policy_version": POLICY,
        "mandate_ref": digest("mandate:dogfood-1"),
        "agent_id": AGENT_DID,
    }
    if spend_cap is not None:
        body["spend_cap"] = spend_cap
    return body


def decision_body() -> dict:
    return {
        "action": "memory.search",
        "action_args_hash": digest("args:search:1"),
        "model": {"provider": "local", "id": "wm-recall"},
        "input_provenance": {
            "policy_id": "egress.default",
            "allowed_sources": ["gate"],
            "observed_sources_hash": digest("sources:gate-only"),
        },
        "decision": "allow",
        "policy_version": POLICY,
    }


def execution_body() -> dict:
    return {
        "tool_calls": [
            {
                "name": "memory.search",
                "args_hash": digest("args:search:1"),
                "result_hash": digest("result:search:1"),
            }
        ],
        "egress": [{"destination": "none", "bytes": 0, "allowed": True}],
        "resources": {"cpu_ms": 1200, "mem_peak_mb": 48, "disk_peak_mb": 8},
        "sandbox_class": "bwrap-landlock",
    }


def delivery_body(spec: str, extra: dict | None = None) -> dict:
    body = {
        "request_hash": digest("request:1"),
        "response_hash": digest("response:1"),
        "counterparty": {"id": COUNTERPARTY_DID},
        "spec_ref": spec,
    }
    if extra:
        body.update(extra)
    return body


def settlement_body(gated=True, minor=200, currency="USD") -> dict:
    return {
        "rail": "invoice",
        "rail_ref": "inv-0001",
        "amount": {"minor": minor, "currency": currency},
        "gated_on_delivery": gated,
        "settled_at": "2026-09-17T21:10:00Z",
    }


def termination_body() -> dict:
    return {
        "reason": "completed",
        "limits_at_stop": {
            "cpu_ms": 300000,
            "wall_ms": 300000,
            "spend_minor": 1000,
            "currency": "USD",
        },
        "remaining": {
            "cpu_ms": 298800,
            "wall_ms": 299000,
            "spend_minor": 800,
            "currency": "USD",
        },
    }


def add(chain: TaskChain, record_type: str, body: dict) -> dict:
    return chain.add(record_type, "gate", GATE_DID, GATE_KEY, body)


def minimal_chain(spec: str, task_id=None) -> TaskChain:
    chain = TaskChain(task_id, spec=spec)
    add(chain, "session.pass.created", pass_body())
    add(chain, "task.decision", decision_body())
    add(chain, "task.execution", execution_body())
    add(chain, "task.termination", termination_body())
    return chain


def full_chain(spec: str, task_id=None) -> TaskChain:
    chain = TaskChain(task_id, spec=spec)
    add(chain, "session.pass.created", pass_body(spend_cap={"minor": 1000, "currency": "USD"}))
    add(chain, "task.decision", decision_body())
    add(chain, "task.execution", execution_body())
    add(chain, "delivery.attestation", delivery_body(spec))
    add(chain, "settlement", settlement_body())
    add(chain, "task.termination", termination_body())
    return chain


def write(output_dir: Path, name: str, bundle: dict) -> str:
    path = output_dir / name
    path.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    return path.name


def generate_vectors(output_dir: Path, spec: str) -> int:
    output_dir = Path(output_dir).resolve()
    if spec not in SPECS:
        raise ValueError(f"unsupported receipt spec: {spec}")
    if output_dir == VECTORS.resolve():
        raise ValueError(f"refusing to overwrite historical vectors at {VECTORS}; choose a separate output directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []

    write(output_dir, "01_happy_minimal.json", minimal_chain(spec).bundle())
    rows.append(("01_happy_minimal.json", "TRUSTED", None, ""))

    write(output_dir, "02_happy_full.json", full_chain(spec).bundle())
    rows.append(("02_happy_full.json", "TRUSTED", None, ""))

    tampered = minimal_chain(spec).bundle()
    tampered["receipts"][2]["body"]["resources"]["cpu_ms"] = 999999
    write(output_dir, "03_tampered_body.json", tampered)
    rows.append(("03_tampered_body.json", "UNTRUSTED", "bad_signature", ""))

    no_term = TaskChain(spec=spec)
    add(no_term, "session.pass.created", pass_body())
    add(no_term, "task.decision", decision_body())
    add(no_term, "task.execution", execution_body())
    write(output_dir, "04_missing_termination.json", no_term.bundle())
    rows.append(("04_missing_termination.json", "UNTRUSTED", "missing_termination", ""))

    over_cap = TaskChain(spec=spec)
    add(over_cap, "session.pass.created", pass_body(spend_cap={"minor": 100, "currency": "USD"}))
    add(over_cap, "task.decision", decision_body())
    add(over_cap, "task.execution", execution_body())
    add(over_cap, "delivery.attestation", delivery_body(spec))
    add(over_cap, "settlement", settlement_body(minor=5000))
    add(over_cap, "task.termination", termination_body())
    write(output_dir, "05_cap_exceeded.json", over_cap.bundle())
    rows.append(("05_cap_exceeded.json", "UNTRUSTED", "cap_exceeded", ""))

    early_settle = TaskChain(spec=spec)
    add(early_settle, "session.pass.created", pass_body())
    add(early_settle, "task.decision", decision_body())
    add(early_settle, "task.execution", execution_body())
    add(early_settle, "settlement", settlement_body())
    add(early_settle, "delivery.attestation", delivery_body(spec))
    add(early_settle, "task.termination", termination_body())
    write(output_dir, "06_delivery_before_settlement.json", early_settle.bundle())
    rows.append(("06_delivery_before_settlement.json", "UNTRUSTED", "delivery_before_settlement", ""))

    salt = keys.random_salt_hex()
    redacted_value = ["quality-ok"]
    redacted_field = {"redacted": True, "commit": commit_field(salt, redacted_value)}

    redacted_chain = TaskChain(spec=spec)
    add(redacted_chain, "session.pass.created", pass_body(spend_cap={"minor": 1000, "currency": "USD"}))
    add(redacted_chain, "task.decision", decision_body())
    add(redacted_chain, "task.execution", execution_body())
    add(redacted_chain, "delivery.attestation", delivery_body(spec, {"quality_flags": redacted_field}))
    add(redacted_chain, "settlement", settlement_body())
    add(redacted_chain, "task.termination", termination_body())
    write(output_dir, "07_redacted_no_disclosure.json", redacted_chain.bundle())
    rows.append(("07_redacted_no_disclosure.json", "PROVISIONAL", None, ""))

    disclosed = redacted_chain.bundle()
    path_key = "receipts[3].body.quality_flags"
    disclosed["disclosure_map"] = {path_key: {"salt": salt, "value": redacted_value}}
    write(output_dir, "08_redacted_disclosed.json", disclosed)
    rows.append(("08_redacted_disclosed.json", "TRUSTED", None, ""))

    erased = TaskChain(spec=spec)
    erased_body = delivery_body(spec,
        {"quality_flags": {"redacted": True, "commit": redacted_field["commit"], "erased": True}}
    )
    add(erased, "session.pass.created", pass_body(spend_cap={"minor": 1000, "currency": "USD"}))
    add(erased, "task.decision", decision_body())
    add(erased, "task.execution", execution_body())
    add(erased, "delivery.attestation", erased_body)
    add(erased, "settlement", settlement_body())
    add(erased, "task.termination", termination_body())
    write(output_dir, "09_erased_content.json", erased.bundle())
    rows.append(("09_erased_content.json", "INSUFFICIENT_EVIDENCE", None, ""))

    anchored = minimal_chain(spec).bundle()
    anchored["anchors"] = [
        {"target": anchored["receipts"][0]["receipt_id"], "hash": "sha256:" + "de" * 32}
    ]
    write(output_dir, "10a_anchor_invalid.json", anchored)
    rows.append(("10a_anchor_invalid.json", "UNTRUSTED", "anchor_invalid", ""))

    write(output_dir, "10b_anchor_missing.json", minimal_chain(spec).bundle())
    rows.append(("10b_anchor_missing.json", "PROVISIONAL", None, "require_anchor"))

    index_lines = [
        f"# Continuity Receipt spec {spec.rsplit('/', 1)[1]} — test vector index",
        "",
        "Generated by `tools/make_vectors.py`. For example:",
        f"`python3 tools/make_vectors.py --spec {spec.rsplit('/', 1)[1]} --out <output-dir>`",
        "Verify with `python3 -m continuity_receipt.verify <output-dir>/<file> [--require-anchor]`.",
        "",
        "| Vector | Expected verdict | Primary error | Notes |",
        "|---|---|---|---|",
    ]
    for name, verdict, code, note in rows:
        index_lines.append(f"| {name} | {verdict} | {code or '—'} | {note} |")
    (output_dir / "INDEX.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")

    print(f"wrote {len(rows)} vectors for {spec} to {output_dir}")
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    spec_choices = (*SPEC_ALIASES, *SPECS)
    parser.add_argument("--spec", required=True, choices=spec_choices, help="receipt spec to generate")
    parser.add_argument("--out", "--output-dir", dest="output_dir", required=True, type=Path,
                        help="new/selected output directory")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    return generate_vectors(args.output_dir, SPEC_ALIASES.get(args.spec, args.spec))


if __name__ == "__main__":
    raise SystemExit(main())
