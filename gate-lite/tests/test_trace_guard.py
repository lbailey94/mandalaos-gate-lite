"""Tests for the PEB-23-style gate-lite trace guard."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gate_lite import trace_guard  # noqa: E402


def step(kind="tool_call", target="t", ok=True, **extra):
    raw = {"type": kind, "target": target, "ok": ok}
    raw.update(extra)
    return raw


class TestTraceGuard(unittest.TestCase):
    def test_clean_trace_passes(self):
        steps = [
            step("plan", target=None),
            step("tool_call", target="read", ok=True),
            step("write", target="src/a.rs", scope="src", ok=True),
            step("claim", evidence="sha256:abc"),
            step("complete", evidence="sha256:abc"),
        ]
        result = trace_guard.guard_trace(steps, allowed_scopes=["src"])
        self.assertTrue(result["ok"], result["violations"])
        self.assertEqual(result["violations"], [])

    def test_scope_confinement_violation(self):
        steps = [step("write", target="/etc/passwd", scope="etc", ok=True)]
        result = trace_guard.guard_trace(steps, allowed_scopes=["src"])
        self.assertFalse(result["ok"])
        self.assertIn("ScopeConfinement", {v["property"] for v in result["violations"]})

    def test_out_of_scope_flag_violation(self):
        steps = [step("tool_call", target="rm", ok=False, out_of_scope=True)]
        result = trace_guard.guard_trace(steps)
        self.assertFalse(result["ok"])
        self.assertIn("ScopeConfinement", {v["property"] for v in result["violations"]})

    def test_anti_thrash_loop_violation_and_shrink(self):
        steps = [step("noise", target=f"n{i}", ok=True) for i in range(20)]
        steps += [step("tool_call", target="deploy", ok=False) for _ in range(3)]
        steps += [step("noise", target="tail", ok=True)]
        result = trace_guard.guard_trace(steps)
        self.assertFalse(result["ok"])
        self.assertIn("AntiThrashLoop", {v["property"] for v in result["violations"]})
        self.assertLess(result["shrunk_len"], result["original_len"])
        self.assertTrue(result["replay_sha256"])

    def test_context_anxiety_guard(self):
        steps = [step("complete", pending_gates=["tests"], evidence="sha256:abc")]
        result = trace_guard.guard_trace(steps)
        self.assertFalse(result["ok"])
        self.assertIn("ContextAnxietyGuard", {v["property"] for v in result["violations"]})

    def test_evidence_before_claim(self):
        steps = [step("claim")]
        result = trace_guard.guard_trace(steps)
        self.assertFalse(result["ok"])
        self.assertIn("EvidenceBeforeClaim", {v["property"] for v in result["violations"]})

    def test_budget_monotonicity(self):
        steps = [step("tool_call", target="a", tokens=60), step("tool_call", target="b", tokens=60)]
        result = trace_guard.guard_trace(steps, budget_tokens=100)
        self.assertFalse(result["ok"])
        self.assertIn("BudgetMonotonicity", {v["property"] for v in result["violations"]})

    def test_shrink_minimizes_large_failing_trace(self):
        steps = [step("noise", target=f"n{i}", ok=True, tokens=1) for i in range(200)]
        steps += [step("write", target="/etc/x", scope="etc", ok=True)]
        steps += [step("noise", target="tail", ok=True)]
        result = trace_guard.guard_trace(steps, allowed_scopes=["src"])
        self.assertFalse(result["ok"])
        self.assertLessEqual(result["shrunk_len"], 3)
        self.assertGreater(result["compression"], 50)

    def test_cli_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.json"
            path.write_text(json.dumps({"steps": [step("claim")]}), encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = trace_guard.main([str(path), "--json"])
            self.assertEqual(rc, 1)
            parsed = json.loads(buf.getvalue())
            self.assertFalse(parsed["ok"])
            self.assertTrue(parsed["replay_sha256"])


if __name__ == "__main__":
    unittest.main()
