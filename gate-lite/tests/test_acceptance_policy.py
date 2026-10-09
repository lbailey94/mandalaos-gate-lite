"""Policy tests for explicit, exact-profile real-runner acceptance opt-in."""
import os
import unittest
from unittest.mock import patch

from acceptance_policy import acceptance_policy
from gate_lite.orchestrator import PROFILE_ID


class TestAcceptancePolicy(unittest.TestCase):
    def test_default_policy_skips_with_actionable_reason(self):
        with patch.dict(os.environ, {}, clear=True):
            policy = acceptance_policy()
        self.assertFalse(policy.runner_enabled)
        self.assertIn("GATE_LITE_REAL_RUNNER_TESTS=1", policy.runner_skip_reason)
        self.assertFalse(policy.quota_enabled)
        self.assertIn("GATE_LITE_QUOTA_TESTS=1", policy.quota_skip_reason)

    def test_invalid_opt_in_without_configured_executable_fails_clearly(self):
        with patch.dict(
            os.environ,
            {"GATE_LITE_REAL_RUNNER_TESTS": "1", "WM_GATELITE_RUNNER": "/missing/runner"},
            clear=True,
        ), patch("acceptance_policy.shutil.which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "requested an invalid runner profile"):
                acceptance_policy()

    def test_opt_in_rejects_unqualified_executable_profile(self):
        fake_runner = type(
            "Runner",
            (),
            {
                "profile_id": None,
                "profile_status": "unqualified",
                "sandbox_class": "unknown",
                "_require_profile": lambda self: None,
            },
        )()
        with patch.dict(
            os.environ,
            {"GATE_LITE_REAL_RUNNER_TESTS": "1", "WM_GATELITE_RUNNER": "/tmp/marker-runner"},
            clear=True,
        ), patch("acceptance_policy.SandboxRunner", return_value=fake_runner):
            with self.assertRaisesRegex(RuntimeError, "exact reviewed wrapper, bwrap, and jq identities"):
                acceptance_policy()

    def test_opt_in_requires_exact_reviewed_profile_and_dependencies(self):
        class ValidRunner:
            profile_id = PROFILE_ID
            profile_status = "locally_qualified"
            sandbox_class = "bwrap"

            def _require_profile(self):
                return None

        with patch.dict(
            os.environ,
            {"GATE_LITE_REAL_RUNNER_TESTS": "1", "WM_GATELITE_RUNNER": "/tmp/qualified-runner"},
            clear=True,
        ), patch("acceptance_policy.SandboxRunner", return_value=ValidRunner()), patch(
            "acceptance_policy.shutil.which", return_value=None
        ):
            policy = acceptance_policy()
        self.assertTrue(policy.runner_enabled)
        self.assertEqual(policy.runner_path, "/tmp/qualified-runner")
        self.assertFalse(policy.quota_enabled)
        self.assertIn("GATE_LITE_QUOTA_TESTS=1", policy.quota_skip_reason)

    def test_quota_opt_in_reports_missing_systemd_prerequisite(self):
        class ValidRunner:
            profile_id = PROFILE_ID
            profile_status = "locally_qualified"
            sandbox_class = "bwrap"

            def _require_profile(self):
                return None

        with patch.dict(
            os.environ,
            {
                "GATE_LITE_REAL_RUNNER_TESTS": "1",
                "GATE_LITE_QUOTA_TESTS": "1",
                "WM_GATELITE_RUNNER": "/tmp/qualified-runner",
            },
            clear=True,
        ), patch("acceptance_policy.SandboxRunner", return_value=ValidRunner()), patch(
            "acceptance_policy.shutil.which", return_value=None
        ):
            policy = acceptance_policy()
        self.assertFalse(policy.quota_enabled)
        self.assertIn("systemd-run, systemctl", policy.quota_skip_reason)

    def test_invalid_opt_in_value_is_not_silently_skipped(self):
        with patch.dict(os.environ, {"GATE_LITE_REAL_RUNNER_TESTS": "yes"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "must be unset, 0, or 1"):
                acceptance_policy()


if __name__ == "__main__":
    unittest.main()
