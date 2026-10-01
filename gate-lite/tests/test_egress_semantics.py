#!/usr/bin/env python3
"""Egress semantics: declared destinations are recorded intent, not enforcement.

When `net: true` and destinations are declared, the current wrapper profile
shares the whole network; the declared list is not an allowlist, and entries
carry `"enforced": false`. Denials are enforced by the netns unshare and carry
`"enforced": true`. These vocabulary guarantees are what receipts rely on, so
they are pinned here without needing a qualified runner.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gate_lite.orchestrator import parse_payload  # noqa: E402


class TestEgressSemantics(unittest.TestCase):
    def test_granted_egress_records_unenforced_destinations(self):
        plan = parse_payload(
            json.dumps(
                {
                    "program": "curl",
                    "args": ["-sS", "https://example.com"],
                    "net": True,
                    "egress": ["example.com", "api.example.org"],
                }
            )
        )
        self.assertTrue(plan["net"])
        self.assertEqual(
            [entry["destination"] for entry in plan["egress"]],
            ["example.com", "api.example.org"],
        )
        for entry in plan["egress"]:
            self.assertTrue(entry["allowed"], entry)
            self.assertFalse(entry["enforced"], entry)
            self.assertIn("whole network", entry["enforcer"])

    def test_net_without_declared_destinations_is_enforced_denial(self):
        plan = parse_payload(
            json.dumps(
                {
                    "program": "curl",
                    "args": ["-sS", "https://example.com"],
                    "net": True,
                    "egress": [],
                }
            )
        )
        self.assertFalse(plan["net"])
        entry = plan["egress"][0]
        self.assertEqual(entry["destination"], "undeclared")
        self.assertFalse(entry["allowed"])
        self.assertTrue(entry["enforced"])
        self.assertEqual(entry["bytes"], 0)

    def test_declared_without_net_is_enforced_denial(self):
        plan = parse_payload(
            json.dumps(
                {
                    "program": "curl",
                    "args": ["-sS", "https://example.com"],
                    "egress": ["example.com"],
                }
            )
        )
        self.assertFalse(plan["net"])
        entry = plan["egress"][0]
        self.assertEqual(entry["destination"], "example.com")
        self.assertFalse(entry["allowed"])
        self.assertTrue(entry["enforced"])

    def test_plain_command_requests_no_egress(self):
        plan = parse_payload("echo hello")
        self.assertFalse(plan["net"])
        self.assertEqual(plan["egress"], [])


if __name__ == "__main__":
    unittest.main()
