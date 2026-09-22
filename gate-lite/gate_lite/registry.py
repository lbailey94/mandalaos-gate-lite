"""SQLite registry for gate-lite v0.1 (replaces the JSON-file prototype).

Why: the JSON registry was O(total slots) per operation — each read reparsed
the whole `state.json`, each write rewrote it (get_slot 0.37 ms @100 slots →
43 ms @10k; put_slot → 315 ms; benchmark evidence
`evidence/bench-2026-09-18/`). Records are still stored as opaque JSON
payloads identically to the old format; only the container changed, so all
callers keep the same API.

Multi-process safety: SQLite WAL + a busy timeout (`timeout=30`) serializes
writers and lets readers proceed concurrently — no external flock file. Each
thread keeps one cached connection, so a shared Registry instance is also
safe under the MCP server's thread pool.

Migration: if the database is empty and a sibling `state.json` exists (the
prototype registry), its sections are imported in one transaction. The JSON
file is left in place, untouched, as a frozen record.
"""
import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

SECTIONS = ("tenants", "slots", "passes", "snapshots", "idempotency")

_ID_KEYS = {
    "tenants": "tenant_id",
    "slots": "slot_id",
    "passes": "pass_id",
    "snapshots": "snapshot_id",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id TEXT PRIMARY KEY,
    json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS slots (
    slot_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS slots_tenant_idx ON slots(tenant_id, slot_id);
CREATE TABLE IF NOT EXISTS passes (
    pass_id TEXT PRIMARY KEY,
    tenant_id TEXT,
    json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS passes_tenant_idx ON passes(tenant_id);
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id TEXT PRIMARY KEY,
    tenant_id TEXT,
    json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS snapshots_tenant_idx ON snapshots(tenant_id);
CREATE TABLE IF NOT EXISTS idempotency (
    key TEXT PRIMARY KEY,
    json TEXT NOT NULL
);
"""


class Registry:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.legacy_path = self.path.parent / "state.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    # -- connection helpers ------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    @contextmanager
    def _connection(self):
        """Yield this thread's cached connection, committing on success.

        WAL is persistent; `synchronous` is per-connection, so it is set on
        every connect. One connection per thread keeps the per-operation
        floor low under the MCP server's thread pool while staying safe
        across processes (WAL serializes writers, readers never block).
        """
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._connect()
            self._local.conn = conn
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    def _init_db(self) -> None:
        with self._connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.executescript(_SCHEMA)
            if self._is_empty(conn) and self.legacy_path.exists():
                self._import_legacy(conn)

    @staticmethod
    def _is_empty(conn: sqlite3.Connection) -> bool:
        for section in SECTIONS:
            count = conn.execute(f"SELECT COUNT(*) AS n FROM {section}").fetchone()["n"]
            if count:
                return False
        return True

    def _import_legacy(self, conn: sqlite3.Connection) -> None:
        loaded = json.loads(self.legacy_path.read_text(encoding="utf-8"))
        for section in SECTIONS:
            records = loaded.get(section)
            if not isinstance(records, dict):
                continue
            if section == "idempotency":
                conn.executemany(
                    "INSERT OR IGNORE INTO idempotency(key, json) VALUES(?, ?)",
                    [(key, json.dumps(value)) for key, value in records.items()],
                )
                continue
            id_key = _ID_KEYS[section]
            conn.executemany(
                f"INSERT OR IGNORE INTO {section}({id_key}, tenant_id, json) VALUES(?, ?, ?)",
                [
                    (record.get(id_key, key), record.get("tenant_id"), json.dumps(record))
                    for key, record in records.items()
                ],
            )

    # -- write helpers -----------------------------------------------------
    @staticmethod
    def _write(conn: sqlite3.Connection, section: str, record: dict) -> None:
        if section == "idempotency":
            raise ValueError("idempotency records are written via remember()/put_many keys")
        id_key = _ID_KEYS[section]
        conn.execute(
            f"INSERT INTO {section}({id_key}, tenant_id, json) VALUES(?, ?, ?) "
            f"ON CONFLICT({id_key}) DO UPDATE SET tenant_id=excluded.tenant_id, json=excluded.json",
            (record[id_key], record.get("tenant_id"), json.dumps(record)),
        )

    def put_many(self, section: str, records: list[dict]) -> None:
        """Insert/replace many records of one section in a single transaction."""
        if section not in SECTIONS or section == "idempotency":
            raise ValueError(f"put_many supports {SECTIONS[:-1]}, not {section!r}")
        with self._connection() as conn:
            for record in records:
                self._write(conn, section, record)

    # -- select helpers ----------------------------------------------------
    @staticmethod
    def _get(conn: sqlite3.Connection, section: str, id_value: str) -> dict | None:
        id_key = _ID_KEYS[section]
        row = conn.execute(
            f"SELECT json FROM {section} WHERE {id_key} = ?", (id_value,)
        ).fetchone()
        return json.loads(row["json"]) if row else None

    @staticmethod
    def _for_tenant(conn: sqlite3.Connection, section: str, tenant_id: str) -> list[dict]:
        rows = conn.execute(
            f"SELECT json FROM {section} WHERE tenant_id = ? ORDER BY {_ID_KEYS[section]}",
            (tenant_id,),
        ).fetchall()
        return [json.loads(row["json"]) for row in rows]

    # -- public API (unchanged signatures) ---------------------------------
    def put_tenant(self, tenant: dict) -> None:
        with self._connection() as conn:
            self._write(conn, "tenants", tenant)

    def get_tenant(self, tenant_id: str) -> dict | None:
        with self._connection() as conn:
            return self._get(conn, "tenants", tenant_id)

    def put_slot(self, slot: dict) -> None:
        with self._connection() as conn:
            self._write(conn, "slots", slot)

    def get_slot(self, slot_id: str) -> dict | None:
        with self._connection() as conn:
            return self._get(conn, "slots", slot_id)

    def cas_slot(
        self,
        slot_id: str,
        expected_states: tuple[str, ...],
        update: dict,
        require=None,
    ) -> dict | None:
        """Atomic compare-and-swap on a slot's state.

        Read-verify-update runs inside one `BEGIN IMMEDIATE` transaction, so
        two writers cannot both pass the check — this is the primitive that
        closes the exec-vs-kill/expiry race (gate-lite issue #1). `require`
        is an optional extra predicate on the stored slot (e.g. "not
        expired"); it must also hold for the swap to apply. Returns the
        updated slot, or None when the state or predicate did not match.
        """
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT json FROM slots WHERE slot_id = ?", (slot_id,)
            ).fetchone()
            if row is None:
                return None
            slot = json.loads(row["json"])
            if slot.get("state") not in expected_states:
                return None
            if require is not None and not require(slot):
                return None
            slot.update(update)
            conn.execute(
                "UPDATE slots SET json = ? WHERE slot_id = ?",
                (json.dumps(slot), slot_id),
            )
            return slot

    def slots_for(self, tenant_id: str) -> list[dict]:
        with self._connection() as conn:
            return self._for_tenant(conn, "slots", tenant_id)

    def all_slots(self, tenant_id: str | None = None) -> list[dict]:
        with self._connection() as conn:
            if tenant_id:
                rows = conn.execute(
                    "SELECT json FROM slots WHERE tenant_id = ? ORDER BY slot_id",
                    (tenant_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT json FROM slots ORDER BY slot_id").fetchall()
        return [json.loads(row["json"]) for row in rows]

    def put_pass(self, record: dict) -> None:
        with self._connection() as conn:
            self._write(conn, "passes", record)

    def get_pass(self, pass_id: str) -> dict | None:
        with self._connection() as conn:
            return self._get(conn, "passes", pass_id)

    def put_snapshot(self, record: dict) -> None:
        with self._connection() as conn:
            self._write(conn, "snapshots", record)

    def get_snapshot(self, snapshot_id: str) -> dict | None:
        with self._connection() as conn:
            return self._get(conn, "snapshots", snapshot_id)

    def snapshots_for(self, tenant_id: str) -> list[dict]:
        with self._connection() as conn:
            return self._for_tenant(conn, "snapshots", tenant_id)

    def remember(self, key: str, value: dict) -> None:
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO idempotency(key, json) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET json=excluded.json",
                (key, json.dumps(value)),
            )

    def recall(self, key: str) -> dict | None:
        with self._connection() as conn:
            row = conn.execute("SELECT json FROM idempotency WHERE key = ?", (key,)).fetchone()
        return json.loads(row["json"]) if row else None

    def reload(self) -> dict:
        """Return the full registry in the legacy dict-of-dicts shape.

        Compatibility shim for callers that still need a snapshot of every
        section; the hot paths use indexed per-record lookups instead.
        """
        data = {section: {} for section in SECTIONS}
        with self._connection() as conn:
            for section in SECTIONS:
                if section == "idempotency":
                    rows = conn.execute("SELECT key, json FROM idempotency ORDER BY key").fetchall()
                    data[section] = {row["key"]: json.loads(row["json"]) for row in rows}
                    continue
                id_key = _ID_KEYS[section]
                rows = conn.execute(
                    f"SELECT {id_key}, json FROM {section} ORDER BY {id_key}"
                ).fetchall()
                data[section] = {row[id_key]: json.loads(row["json"]) for row in rows}
        return data
