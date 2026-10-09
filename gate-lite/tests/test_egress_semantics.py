"""Receipt vocabulary records egress intent separately from enforcement."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gate_lite.orchestrator import parse_payload  # noqa: E402


class TestEgressSemantics(unittest.TestCase):
    def test_declared_destinations_are_intent_with_whole_network_access(self):
        plan = parse_payload(json.dumps({
            "program": "curl", "args": ["https://example.com"],
            "net": True, "egress": ["example.com", "api.example.org"],
        }))
        self.assertTrue(plan["net"])
        self.assertEqual([entry["destination"] for entry in plan["egress"]],
                         ["example.com", "api.example.org"])
        for entry in plan["egress"]:
            self.assertTrue(entry["allowed"], entry)
            self.assertFalse(entry["enforced"], entry)
            self.assertIn("whole network", entry["enforcer"])

    def test_network_request_without_destinations_is_enforced_denial(self):
        plan = parse_payload(json.dumps({"program": "curl", "net": True, "egress": []}))
        self.assertFalse(plan["net"])
        entry = plan["egress"][0]
        self.assertEqual(entry["destination"], "undeclared")
        self.assertFalse(entry["allowed"])
        self.assertTrue(entry["enforced"])
        self.assertEqual(entry["bytes"], 0)

    def test_destinations_without_network_request_are_enforced_denial(self):
        plan = parse_payload(json.dumps({"program": "curl", "egress": ["example.com"]}))
        entry = plan["egress"][0]
        self.assertFalse(plan["net"])
        self.assertFalse(entry["allowed"])
        self.assertTrue(entry["enforced"])
        self.assertEqual(entry["enforcer"], "bwrap --unshare-net")

    def test_plain_command_has_no_egress_request(self):
        plan = parse_payload("echo hello")
        self.assertFalse(plan["net"])
        self.assertEqual(plan["egress"], [])


if __name__ == "__main__":
    unittest.main()
