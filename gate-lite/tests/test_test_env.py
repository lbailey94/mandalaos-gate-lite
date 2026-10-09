"""Regression coverage for isolation of runner-sensitive subprocess tests."""
import os
import unittest
from unittest.mock import patch

from test_env import RUNNER_SELECTION_ENV, controlled_test_env


class TestControlledTestEnvironment(unittest.TestCase):
    def test_polluted_runner_hints_are_cleared_but_path_and_python_imports_survive(self):
        polluted = {name: f"polluted-{name}" for name in RUNNER_SELECTION_ENV}
        polluted.update({"WM_MANDALA_SANDBOX_CLASS": "bwrap", "WM_SANDBOX_CLASS": "bwrap"})
        polluted.update({"PATH": "/test/bin", "PYTHONPATH": "/test/python", "VIRTUAL_ENV": "/test/venv"})
        with patch.dict(os.environ, polluted, clear=True):
            clean = controlled_test_env()
            self.assertEqual(clean["PATH"], "/test/bin")
            self.assertEqual(clean["PYTHONPATH"], "/test/python")
            self.assertEqual(clean["VIRTUAL_ENV"], "/test/venv")
            self.assertTrue(all(name not in clean for name in RUNNER_SELECTION_ENV))

    def test_intentional_runner_overrides_are_restored_after_scrubbing(self):
        with patch.dict(os.environ, {"WM_GATELITE_RUNNER": "/polluted", "WM_GATELITE_SLICE": "1"}, clear=True):
            clean = controlled_test_env(
                overrides={"WM_GATELITE_RUNNER": "/intentional", "WM_GATELITE_SLICE": None}
            )
        self.assertEqual(clean["WM_GATELITE_RUNNER"], "/intentional")
        self.assertNotIn("WM_GATELITE_SLICE", clean)


if __name__ == "__main__":
    unittest.main()
