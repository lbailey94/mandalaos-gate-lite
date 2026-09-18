"""Gate-lite registry tests: SQLite storage, tenant scoping, legacy migration."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gate_lite.registry import Registry  # noqa: E402


def slot(slot_id: str, tenant_id: str) -> dict:
    return {
        "slot_id": slot_id,
        "tenant_id": tenant_id,
        "state": "active",
        "expires_at": 1800000000,
    }


class TestRegistry(unittest.TestCase):
    def test_roundtrip_all_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = Registry(Path(tmp) / "registry.db")
            registry.put_tenant({"tenant_id": "t1", "agents": ["did:key:zAgent"]})
            registry.put_slot(slot("slot-1", "t1"))
            registry.put_pass({"pass_id": "pass-1", "slot_id": "slot-1", "tenant_id": "t1"})
            registry.put_snapshot({"snapshot_id": "snap-1", "tenant_id": "t1", "tree_hash": "sha256:x"})
            registry.remember("pass:idem-1", {"slot_id": "slot-1"})

            self.assertEqual(registry.get_tenant("t1")["agents"], ["did:key:zAgent"])
            self.assertEqual(registry.get_slot("slot-1")["state"], "active")
            self.assertEqual(registry.get_pass("pass-1")["tenant_id"], "t1")
            self.assertEqual(registry.get_snapshot("snap-1")["tree_hash"], "sha256:x")
            self.assertEqual(registry.recall("pass:idem-1"), {"slot_id": "slot-1"})
            self.assertIsNone(registry.get_slot("missing"))
            self.assertIsNone(registry.recall("missing"))

    def test_persistence_across_instances(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.db"
            Registry(path).put_slot(slot("slot-1", "t1"))
            self.assertEqual(Registry(path).get_slot("slot-1")["slot_id"], "slot-1")

    def test_tenant_scoping_and_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = Registry(Path(tmp) / "registry.db")
            registry.put_many("slots", [slot("slot-b", "t1"), slot("slot-a", "t1"), slot("slot-c", "t2")])
            self.assertEqual([s["slot_id"] for s in registry.slots_for("t1")], ["slot-a", "slot-b"])
            self.assertEqual([s["slot_id"] for s in registry.all_slots()], ["slot-a", "slot-b", "slot-c"])
            self.assertEqual([s["slot_id"] for s in registry.all_slots("t2")], ["slot-c"])

    def test_put_many_replaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = Registry(Path(tmp) / "registry.db")
            registry.put_many("slots", [slot("slot-1", "t1")])
            updated = slot("slot-1", "t1")
            updated["state"] = "terminated"
            registry.put_many("slots", [updated])
            self.assertEqual(registry.get_slot("slot-1")["state"], "terminated")

    def test_corrupt_idempotency_record_survives_upsert(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = Registry(Path(tmp) / "registry.db")
            registry.remember("k", {"n": 1})
            registry.remember("k", {"n": 2})
            self.assertEqual(registry.recall("k"), {"n": 2})

    def test_legacy_json_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            legacy = {
                "tenants": {"t1": {"tenant_id": "t1", "agents": []}},
                "slots": {"slot-1": slot("slot-1", "t1")},
                "passes": {"pass-1": {"pass_id": "pass-1", "tenant_id": "t1"}},
                "snapshots": {"snap-1": {"snapshot_id": "snap-1", "tenant_id": "t1"}},
                "idempotency": {"pass:idem-1": {"slot_id": "slot-1"}},
            }
            legacy_path = state / "state.json"
            legacy_path.write_text(json.dumps(legacy, indent=2, sort_keys=True), encoding="utf-8")

            registry = Registry(state / "registry.db")
            self.assertEqual(registry.get_tenant("t1")["tenant_id"], "t1")
            self.assertEqual(registry.get_slot("slot-1")["slot_id"], "slot-1")
            self.assertEqual(registry.get_pass("pass-1")["pass_id"], "pass-1")
            self.assertEqual(registry.get_snapshot("snap-1")["snapshot_id"], "snap-1")
            self.assertEqual(registry.recall("pass:idem-1"), {"slot_id": "slot-1"})
            self.assertTrue(legacy_path.exists(), "legacy file must be left in place")

            registry.put_slot(slot("slot-2", "t1"))
            reopened = Registry(state / "registry.db")
            self.assertEqual(len(reopened.all_slots()), 2, "reopen must not re-import")

    def test_reload_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = Registry(Path(tmp) / "registry.db")
            registry.put_slot(slot("slot-1", "t1"))
            registry.remember("k", {"n": 1})
            data = registry.reload()
            self.assertEqual(set(data), {"tenants", "slots", "passes", "snapshots", "idempotency"})
            self.assertEqual(data["slots"]["slot-1"]["tenant_id"], "t1")
            self.assertEqual(data["idempotency"]["k"], {"n": 1})


if __name__ == "__main__":
    unittest.main()
