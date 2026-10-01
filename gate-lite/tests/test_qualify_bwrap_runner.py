"""Adversarial, fake-executable tests for the bounded bwrap evidence probe."""
import json
import importlib.util
import tempfile
import unittest
from pathlib import Path

TOOL_PATH = Path(__file__).resolve().parents[1] / "tools" / "qualify_bwrap_runner.py"
TOOL_SPEC = importlib.util.spec_from_file_location("qualify_bwrap_runner", TOOL_PATH)
assert TOOL_SPEC and TOOL_SPEC.loader
qualify_bwrap_runner = importlib.util.module_from_spec(TOOL_SPEC)
TOOL_SPEC.loader.exec_module(qualify_bwrap_runner)
FIXED_PROBE = qualify_bwrap_runner.FIXED_PROBE
FIXED_PROBE_ARG = qualify_bwrap_runner.FIXED_PROBE_ARG
qualify = qualify_bwrap_runner.qualify
sha256_file = qualify_bwrap_runner.sha256_file


PASS_FACTS = {
    "net_namespace_isolated": True,
    "mount_namespace_isolated": True,
    "workspace_mount": {"mountpoint": "/workspace", "options": ["ro", "relatime"], "filesystem": "ext4"},
    "workspace_write_denied": True,
    "tmp_mount": {"mountpoint": "/tmp", "options": ["rw"], "filesystem": "tmpfs"},
    "tmp_write_succeeded": True,
}


class QualifyBwrapTests(unittest.TestCase):
    def fixture(self, root: Path, facts: dict = PASS_FACTS):
        wrapper = root / "mandala-sandbox"
        bwrap = root / "bwrap"
        wrapper_source = r'''#!/usr/bin/python3
import json, os, subprocess, sys
if sys.argv[1] != "--exec": sys.exit(64)
envelope = json.loads(sys.argv[2])
assert envelope["program"] == "/usr/bin/python3"
assert envelope["args"] == ["-c", os.environ["EXPECTED_FIXED_PROBE_ARG"]]
assert envelope["net"] is False and envelope["rw"] is False
if os.environ.get("MUTATE_WRAPPER_DURING_RUN") == "1":
    with open(__file__, "a", encoding="utf-8") as f: f.write("\\n# changed during probe\\n")
argv = ["bwrap", "--unshare-all", "--ro-bind", envelope["workspace"], "/workspace",
        "--tmpfs", "/tmp", "--die-with-parent", "--", envelope["program"], *envelope["args"]]
result = subprocess.run(argv, capture_output=True, text=True)
sys.stdout.write(result.stdout)
sys.stderr.write(result.stderr)
sys.exit(result.returncode)
'''
        # Inject the fixed source in the fake wrapper's environment so the
        # fixture can verify the tool never substitutes caller payload.
        wrapper.write_text(wrapper_source, encoding="utf-8")
        wrapper.chmod(0o700)
        bwrap_source = r'''#!/usr/bin/python3
import json, os, sys
if sys.argv[1:] == ["--version"]:
    print("bubblewrap fake 1")
else:
    if os.environ.get("MUTATE_BWRAP_DURING_RUN") == "1":
        with open(__file__, "a", encoding="utf-8") as f: f.write("\\n# changed during probe\\n")
    print(os.environ["FAKE_FACTS"])
'''
        bwrap.write_text(bwrap_source, encoding="utf-8")
        bwrap.chmod(0o700)
        return wrapper, bwrap

    def run_fixture(self, root: Path, facts: dict = PASS_FACTS, *, mutate_wrapper: bool = False,
                    mutate_bwrap: bool = False, pin_bwrap: bool = True):
        wrapper, bwrap = self.fixture(root, facts)
        # Fake wrapper checks the exact fixed code via the dedicated env value.
        import os

        old_probe, old_facts = os.environ.get("EXPECTED_FIXED_PROBE_ARG"), os.environ.get("FAKE_FACTS")
        old_mutate = os.environ.get("MUTATE_WRAPPER_DURING_RUN")
        old_mutate_bwrap = os.environ.get("MUTATE_BWRAP_DURING_RUN")
        os.environ["EXPECTED_FIXED_PROBE_ARG"] = FIXED_PROBE_ARG
        os.environ["FAKE_FACTS"] = json.dumps(facts)
        if mutate_wrapper:
            os.environ["MUTATE_WRAPPER_DURING_RUN"] = "1"
        else:
            os.environ.pop("MUTATE_WRAPPER_DURING_RUN", None)
        if mutate_bwrap:
            os.environ["MUTATE_BWRAP_DURING_RUN"] = "1"
        else:
            os.environ.pop("MUTATE_BWRAP_DURING_RUN", None)
        try:
            result = qualify(
                str(wrapper), expected_wrapper_sha256=sha256_file(wrapper),
                expected_bwrap_sha256=sha256_file(bwrap) if pin_bwrap else None,
                bwrap_path=str(bwrap),
            )
        finally:
            if old_probe is None:
                os.environ.pop("EXPECTED_FIXED_PROBE_ARG", None)
            else:
                os.environ["EXPECTED_FIXED_PROBE_ARG"] = old_probe
            if old_facts is None:
                os.environ.pop("FAKE_FACTS", None)
            else:
                os.environ["FAKE_FACTS"] = old_facts
            if old_mutate is None:
                os.environ.pop("MUTATE_WRAPPER_DURING_RUN", None)
            else:
                os.environ["MUTATE_WRAPPER_DURING_RUN"] = old_mutate
            if old_mutate_bwrap is None:
                os.environ.pop("MUTATE_BWRAP_DURING_RUN", None)
            else:
                os.environ["MUTATE_BWRAP_DURING_RUN"] = old_mutate_bwrap
        return result, wrapper, bwrap

    def test_passed_fixed_probe_captures_identity_argv_and_open_classification(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence, wrapper, bwrap = self.run_fixture(Path(tmp))
            self.assertEqual(evidence["probe_status"], "PASS")
            self.assertEqual(evidence["classification_status"], "OPEN")
            self.assertEqual(evidence["conclusion"], "OPEN")
            self.assertEqual(evidence["wrapper"]["sha256"], sha256_file(wrapper))
            self.assertEqual(evidence["bwrap"]["sha256"], sha256_file(bwrap))
            self.assertTrue(evidence["bwrap"]["digest_pinned"])
            self.assertEqual(evidence["invocation"]["bwrap_argv"]["argv0"], "bwrap")
            self.assertIn("--unshare-all", evidence["invocation"]["bwrap_argv"]["argv"])
            self.assertTrue(evidence["invocation"]["payload_is_fixed_probe"])
            self.assertFalse(evidence["probes"]["outbound_egress_denial_tested"])

    def test_observed_bwrap_hash_without_expected_digest_is_explicitly_unpinned(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence, _wrapper, _bwrap = self.run_fixture(Path(tmp), pin_bwrap=False)
            self.assertEqual(evidence["probe_status"], "PASS")
            self.assertFalse(evidence["bwrap"]["digest_pinned"])
            self.assertIsNone(evidence["bwrap"]["expected_sha256"])

    def test_failed_namespace_or_write_probe_is_not_qualified(self):
        facts = dict(PASS_FACTS)
        facts["net_namespace_isolated"] = False
        facts["workspace_write_denied"] = False
        with tempfile.TemporaryDirectory() as tmp:
            evidence, _wrapper, _bwrap = self.run_fixture(Path(tmp), facts)
            self.assertEqual(evidence["probe_status"], "FAIL")
            self.assertFalse(evidence["probes"]["checks"]["network_namespace_isolated"])
            self.assertFalse(evidence["probes"]["checks"]["workspace_write_denied"])
            self.assertEqual(evidence["classification_status"], "OPEN")

    def test_changed_wrapper_digest_is_rejected_before_probe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wrapper, bwrap = self.fixture(root)
            original_digest = sha256_file(wrapper)
            wrapper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            wrapper.chmod(0o700)
            evidence = qualify(
                str(wrapper), expected_wrapper_sha256=original_digest,
                expected_bwrap_sha256=sha256_file(bwrap), bwrap_path=str(bwrap),
            )
            self.assertEqual(evidence["probe_status"], "FAIL")
            self.assertIn("wrapper digest", evidence["failure"])

    def test_bwrap_digest_mismatch_is_rejected_before_wrapper_invocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            wrapper, bwrap = self.fixture(Path(tmp))
            evidence = qualify(
                str(wrapper), expected_wrapper_sha256=sha256_file(wrapper),
                expected_bwrap_sha256="sha256:" + "0" * 64, bwrap_path=str(bwrap),
            )
            self.assertEqual(evidence["probe_status"], "FAIL")
            self.assertIn("bwrap digest", evidence["failure"])
            self.assertNotIn("argv", evidence["invocation"])

    def test_changed_wrapper_during_probe_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence, _wrapper, _bwrap = self.run_fixture(Path(tmp), mutate_wrapper=True)
            self.assertEqual(evidence["probe_status"], "FAIL")
            self.assertIn("wrapper identity changed", evidence["failure"])

    def test_changed_bwrap_during_probe_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence, _wrapper, _bwrap = self.run_fixture(Path(tmp), mutate_bwrap=True)
            self.assertEqual(evidence["probe_status"], "FAIL")
            self.assertIn("bwrap identity changed", evidence["failure"])

    def test_missing_bwrap_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            wrapper = Path(tmp) / "wrapper"
            wrapper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            wrapper.chmod(0o700)
            evidence = qualify(str(wrapper), expected_wrapper_sha256=sha256_file(wrapper),
                               bwrap_path=str(Path(tmp) / "missing"))
            self.assertEqual(evidence["probe_status"], "FAIL")
            self.assertTrue(evidence["failure"])


if __name__ == "__main__":
    unittest.main()
