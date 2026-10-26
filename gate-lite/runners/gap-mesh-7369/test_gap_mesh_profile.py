#!/usr/bin/env python3
"""Verification suite for the Wire Protocol 7369 Sovereign Mesh Runner Profile."""
import json
from pathlib import Path
import unittest

PROFILE_PATH = Path(__file__).resolve().parent / "runner-profile-gap-mesh.json"


class TestGapMeshRunnerProfile(unittest.TestCase):
    def setUp(self):
        self.assertTrue(PROFILE_PATH.exists(), "runner-profile-gap-mesh.json must exist")
        self.profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        self.readme = PROFILE_PATH.with_name("README.md").read_text(encoding="utf-8")

    def test_proposal_is_explicitly_non_executable(self):
        self.assertEqual(self.profile["profile_id"], "urn:mandala:runner-profile:gap-mesh-7369")
        self.assertEqual(self.profile["status"], "declarative_only")
        self.assertFalse(self.profile["execution_enabled"])
        self.assertNotIn("sandbox_class", self.profile)
        self.assertIn("No TCP destination/port mediation is implemented.", self.profile["unsupported_reasons"])
        self.assertIn("declarative only; execution unavailable", self.readme)

    def test_network_fields_are_proposal_intent_only(self):
        net = self.profile["network_policy"]
        self.assertEqual(net["permitted_ports"], [7369])
        self.assertEqual(net["protocol"], "rfc-7369-gap-junction")
        self.assertFalse(net["cloud_egress_permitted"])
        self.assertFalse(net["dns_permitted"])

    def test_environment_values_are_not_presented_as_enforcement(self):
        env = self.profile["environment"]
        self.assertEqual(env["WM_MESH_PORT"], "7369")
        self.assertEqual(self.profile["provenance"]["status"], "proposal; no runtime enforcement evidence")
        self.assertIn("Setting environment", self.readme)


if __name__ == "__main__":
    unittest.main()
