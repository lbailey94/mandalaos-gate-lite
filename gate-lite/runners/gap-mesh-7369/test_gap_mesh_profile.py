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

    def test_profile_id_and_schema(self):
        self.assertEqual(self.profile["profile_id"], "urn:mandala:runner-profile:gap-mesh-7369")
        self.assertEqual(self.profile["sandbox_class"], "bwrap")

    def test_network_policy_restricts_to_port_7369(self):
        net = self.profile["network_policy"]
        self.assertEqual(net["permitted_ports"], [7369])
        self.assertEqual(net["protocol"], "rfc-7369-gap-junction")
        self.assertFalse(net["cloud_egress_permitted"])
        self.assertFalse(net["dns_permitted"])

    def test_environment_specifies_mesh_flags(self):
        env = self.profile["environment"]
        self.assertEqual(env["WM_MESH_PORT"], "7369")
        self.assertEqual(env["WM_SANDBOXED"], "1")
        self.assertEqual(env["WM_MESH_PROFILE"], "gap-junction-7369")


if __name__ == "__main__":
    unittest.main()
