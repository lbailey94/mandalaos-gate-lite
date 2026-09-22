"""Gate-lite orchestrator v0: pass → exec → settle → terminate with Continuity Receipts."""
import hashlib
import json
import os
import shlex
import signal as signal_mod
import subprocess
import tarfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from continuity_receipt import records
from continuity_receipt.bundle import TaskChain
from continuity_receipt.canon import sha256_prefixed

from .models import SLOT_CLASSES, Slot, Tenant, now_epoch
from .registry import Registry
from .tokens import issue_pass

POLICY_VERSION = "2026-09-17.1"
GATE_CLASS = "gate-lite"
BLOCKED_STATES = ("terminated", "expired", "denied", "frozen")
CPU_QUOTA_PERCENT = {"small": 100, "medium": 200}
TERMINAL_STATES = ("terminated", "expired", "denied")
# Lifecycle transitions that are in flight (issue #1): a start may not be
# sealed and a seal may not be started while one of these is held. `starting`
# is written by the atomic start CAS before any receipt or side effect;
# `terminating` reserves a terminal transition so a concurrent start cannot
# slip between the read and the seal.
STARTING_STATE = "starting"
TERMINATING_STATE = "terminating"
PRE_START_STATES = ("placed", "active")
# States an idle seal may start from. `frozen` is a static non-terminal state
# (snapshot attestation), not an in-flight transition, so it stays sealable.
IDLE_SEALABLE_STATES = ("placed", "active", "frozen")


class EmitterError(RuntimeError):
    """Receipt emitter unavailable — the gate fails closed (no unrecorded work)."""


def rfc3339(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def tree_hash(root: Path) -> str:
    """Deterministic hash over file names + contents under `root`."""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(root)).encode("utf-8"))
            digest.update(b"\x00")
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return "sha256:" + digest.hexdigest()


def _safe_extract(tar: tarfile.TarFile, target: Path) -> None:
    target = target.resolve()
    for member in tar.getmembers():
        member_path = (target / member.name).resolve()
        if member_path != target and not str(member_path).startswith(str(target) + os.sep):
            raise ValueError(f"unsafe path in snapshot archive: {member.name}")
        if member.issym() or member.islnk() or member.isdev():
            raise ValueError(f"unsupported entry in snapshot archive: {member.name}")
    try:
        tar.extractall(target, filter="data")
    except TypeError:
        tar.extractall(target)


@dataclass
class ExecResult:
    exit_code: int
    stdout_hash: str
    artifacts: list = field(default_factory=list)
    resources: dict = field(default_factory=dict)
    egress: list = field(default_factory=list)
    stderr_hash: str | None = None
    killed_by: str | None = None


def parse_payload(payload_ref: str) -> dict:
    """Payload is a plain command or a declared-execution envelope.

    Envelope: {"program": "curl", "args": [...], "net": true,
               "egress": ["example.com"]}. Egress is default-deny: network is
    shared only when `net` is true AND destinations are declared. Undeclared
    attempts run without network and are recorded as denied.
    """
    text = payload_ref.strip()
    if text.startswith("{"):
        data = json.loads(text)
        if not isinstance(data, dict) or not data.get("program"):
            raise ValueError("payload envelope needs a 'program'")
        program = str(data["program"])
        args = [str(arg) for arg in (data.get("args") or [])]
        wants_net = bool(data.get("net"))
        declared = [str(dest) for dest in (data.get("egress") or [])]
    else:
        parts = shlex.split(text)
        if not parts:
            raise ValueError("empty payload")
        program, args = parts[0], parts[1:]
        wants_net, declared = False, []

    allowed_net = wants_net and bool(declared)
    egress = [
        {
            "destination": dest,
            "bytes": None if allowed_net else 0,
            "allowed": allowed_net,
            "enforcer": "bwrap --share-net" if allowed_net else "bwrap --unshare-net",
        }
        for dest in declared
    ]
    if wants_net and not declared:
        egress = [
            {
                "destination": "undeclared",
                "bytes": 0,
                "allowed": False,
                "enforcer": "bwrap --unshare-net",
                "denied_reason": "net requested without declared destinations",
            }
        ]
    return {
        "program": program,
        "args": args,
        "net": allowed_net,
        "requested_net": wants_net,
        "declared": declared,
        "egress": egress,
    }


def _plan_envelope(plan: dict) -> str:
    envelope = {
        "schema": "wm-sandbox-exec-v1",
        "program": plan["program"],
        "args": plan["args"],
        "net": plan["net"],
    }
    workspace = plan.get("workspace")
    if workspace:
        envelope["workspace"] = workspace
        envelope["rw"] = bool(plan.get("rw", True))
    return json.dumps(envelope)


class StubRunner:
    """Deterministic runner for tests and dogfood dry-runs."""

    sandbox_class = "stub"

    def run(self, slot: dict, payload_ref: str, on_spawn=None) -> ExecResult:
        return ExecResult(
            exit_code=0,
            stdout_hash=sha256_prefixed(("stub:" + payload_ref).encode()),
            resources={"cpu_ms": 900, "mem_peak_mb": 32, "disk_peak_mb": 4},
            egress=[{"destination": "none", "bytes": 0, "allowed": True}],
        )


class SandboxRunner:
    """Invokes the host containment wrapper (`mandala-sandbox --exec`).

    Enable with `WM_GATELITE_RUNNER=/path/to/mandala-sandbox`. Payload refs are
    commands or declared-execution envelopes (see `parse_payload`); network is
    default-deny and enforcement is the wrapper's netns unshare.
    """

    sandbox_class = "bwrap-landlock"

    def __init__(self, runner_path: str):
        self.runner_path = runner_path

    def _argv(self, plan: dict) -> list[str]:
        return [self.runner_path, "--exec", _plan_envelope(plan)]

    def _wall_seconds(self, slot: dict) -> int:
        return max(int(slot["quotas"].get("wall_ms", 60000) / 1000), 1)

    def _popen(self, slot: dict, plan: dict):
        return subprocess.Popen(
            self._argv(plan),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            start_new_session=True,
        )

    def _terminate(self, proc) -> None:
        try:
            os.killpg(os.getpgid(proc.pid), signal_mod.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    def _inspect_kill(self, slot: dict, proc) -> str | None:
        return None

    def _result(self, plan: dict, exit_code: int, stdout: bytes, stderr: bytes,
                killed_by: str | None = None, resources: dict | None = None) -> ExecResult:
        return ExecResult(
            exit_code=exit_code,
            stdout_hash=sha256_prefixed(stdout),
            resources=resources or {"cpu_ms": 0, "mem_peak_mb": 0, "disk_peak_mb": 0},
            egress=[dict(entry) for entry in plan["egress"]],
            stderr_hash=sha256_prefixed(stderr),
            killed_by=killed_by,
        )

    def run(self, slot: dict, payload_ref: str, on_spawn=None) -> ExecResult:
        plan = parse_payload(payload_ref)
        if slot.get("workspace"):
            plan["workspace"] = slot["workspace"]
        proc = self._popen(slot, plan)
        if on_spawn:
            on_spawn(proc.pid, os.getpgid(proc.pid), getattr(proc, "unit", None))
        timed_out = False
        try:
            stdout, stderr = proc.communicate(timeout=self._wall_seconds(slot) + 10)
        except subprocess.TimeoutExpired:
            self._terminate(proc)
            stdout, stderr = proc.communicate()
            timed_out = True
        killed_by = self._inspect_kill(slot, proc)
        if timed_out and killed_by is None:
            killed_by = "wall"
        exit_code = 137 if killed_by else proc.returncode
        return self._result(plan, exit_code, stdout or b"", stderr or b"", killed_by=killed_by)


class SliceRunner(SandboxRunner):
    """SandboxRunner under a systemd user service with cgroup quotas (G2).

    `MemoryMax` overruns become `Result=oom-kill`, `RuntimeMaxSec` overruns
    `Result=timeout`; both map to a quota kill. CPUQuota is a rate throttle,
    not a kill (documented behavior).
    """

    sandbox_class = "bwrap-landlock+systemd-slice"

    def __init__(self, runner_path: str, cpu_percent: int | None = None):
        super().__init__(runner_path)
        self.cpu_percent = cpu_percent

    def _popen(self, slot: dict, plan: dict):
        unit = f"mandala-{slot['slot_id']}-{uuid.uuid4().hex[:6]}"
        quotas = slot["quotas"]
        cpu = self.cpu_percent or CPU_QUOTA_PERCENT.get(slot.get("slot_class", "small"), 100)
        argv = [
            "systemd-run",
            "--user",
            "--unit",
            unit,
            "--wait",
            "--pipe",
            "--quiet",
            "-p",
            f"MemoryMax={max(int(quotas.get('mem_mb', 1024)), 16)}M",
            "-p",
            "MemorySwapMax=0",
            "-p",
            f"CPUQuota={cpu}%",
            "-p",
            f"RuntimeMaxSec={self._wall_seconds(slot)}s",
            "-p",
            "TimeoutStopSec=5s",
            *self._argv(plan),
        ]
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            start_new_session=True,
        )
        proc.unit = unit
        return proc

    def _terminate(self, proc) -> None:
        subprocess.run(
            ["systemctl", "--user", "kill", "--kill-whom=all", "-s", "SIGKILL", proc.unit],
            capture_output=True,
        )

    def _inspect_kill(self, slot: dict, proc) -> str | None:
        show = subprocess.run(
            ["systemctl", "--user", "show", proc.unit, "-p", "Result", "-p", "MemoryPeak", "--value"],
            capture_output=True,
            text=True,
        )
        subprocess.run(["systemctl", "--user", "reset-failed", proc.unit], capture_output=True)
        lines = [line.strip() for line in show.stdout.splitlines() if line.strip()]
        result = lines[0] if lines else ""
        if len(lines) > 1 and lines[1].isdigit():
            bytes_peak = int(lines[1])
            proc.mem_peak_mb = bytes_peak // (1024 * 1024)
        if result == "oom-kill":
            return "memory_max"
        if result == "timeout":
            return "wall"
        return None

    def run(self, slot: dict, payload_ref: str, on_spawn=None) -> ExecResult:
        plan = parse_payload(payload_ref)
        if slot.get("workspace"):
            plan["workspace"] = slot["workspace"]
        proc = self._popen(slot, plan)
        if on_spawn:
            on_spawn(proc.pid, os.getpgid(proc.pid), getattr(proc, "unit", None))
        try:
            stdout, stderr = proc.communicate(timeout=self._wall_seconds(slot) + 15)
        except subprocess.TimeoutExpired:
            self._terminate(proc)
            stdout, stderr = proc.communicate()
        killed_by = self._inspect_kill(slot, proc)
        exit_code = 137 if killed_by else proc.returncode
        resources = {
            "cpu_ms": 0,
            "mem_peak_mb": getattr(proc, "mem_peak_mb", 0),
            "disk_peak_mb": 0,
        }
        return self._result(plan, exit_code, stdout or b"", stderr or b"", killed_by=killed_by, resources=resources)


def build_runner(runner_path: str | None, slice_mode: bool = False):
    if not runner_path:
        return None
    return SliceRunner(runner_path) if slice_mode else SandboxRunner(runner_path)


class Orchestrator:
    def __init__(
        self,
        state_dir,
        gate_id: str = "gate-lite-1",
        gate_key=None,
        gate_did: str | None = None,
        runner=None,
    ):
        from continuity_receipt import keys

        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.receipts_dir = self.state_dir / "receipts"
        self.receipts_dir.mkdir(exist_ok=True)
        self.runs_dir = self.state_dir / "runs"
        self.runs_dir.mkdir(exist_ok=True)
        self.kills_dir = self.state_dir / "kills"
        self.kills_dir.mkdir(exist_ok=True)
        self.workspaces_dir = self.state_dir / "workspaces"
        self.workspaces_dir.mkdir(exist_ok=True)
        self.snapshots_dir = self.state_dir / "snapshots"
        self.snapshots_dir.mkdir(exist_ok=True)
        self.registry = Registry(self.state_dir / "registry.db")

        key_path = self.state_dir / "gate.key"
        if gate_key is None and key_path.exists():
            gate_key = keys.private_from_raw(key_path.read_bytes())
            os.chmod(key_path, 0o600)
        if gate_key is None:
            gate_did, gate_key = keys.generate()
            key_path.write_bytes(keys.private_raw(gate_key))
            os.chmod(key_path, 0o600)
        if gate_did is None:
            gate_did = keys.pubkey_to_did_key(gate_key.public_key())

        self.gate_id = gate_id
        self.gate_did = gate_did
        self.gate_key = gate_key
        self.runner = runner or StubRunner()
        self.policy_version = POLICY_VERSION
        self._chains: dict[str, TaskChain] = {}
        self._last_exec: dict[str, ExecResult] = {}

    # -- registry helpers -------------------------------------------------
    def add_tenant(self, tenant_id: str, agents: list[str], **kwargs) -> dict:
        tenant = Tenant(tenant_id=tenant_id, agents=agents, **kwargs)
        record = dict(tenant.__dict__)
        self.registry.put_tenant(record)
        return record

    # -- run journal (operator kill seam) ---------------------------------
    def _run_path(self, slot_id: str) -> Path:
        return self.runs_dir / f"{slot_id}.json"

    def _kill_path(self, slot_id: str) -> Path:
        return self.kills_dir / f"{slot_id}.json"

    def _journal_run(
        self, slot_id: str, pid: int, pgid: int, unit: str | None, run_generation: int
    ) -> None:
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self._run_path(slot_id).write_text(
            json.dumps(
                {
                    "slot_id": slot_id,
                    "pid": pid,
                    "pgid": pgid,
                    "unit": unit,
                    "run_generation": run_generation,
                    "started_at_ms": int(time.time() * 1000),
                }
            ),
            encoding="utf-8",
        )

    def active_run(self, slot_id: str) -> dict | None:
        path = self._run_path(slot_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _consume_kill_request(self, slot_id: str) -> dict | None:
        path = self._kill_path(slot_id)
        if not path.exists():
            return None
        try:
            request = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            request = {}
        path.unlink(missing_ok=True)
        return request

    def _write_kill_request(
        self, slot_id: str, signal_name: str, run_generation: int | None
    ) -> dict:
        """Bind an operator kill request to a specific run generation.

        The generation binding is what stops a late start from consuming an
        old request (gate-lite issue #1): `exec_` only honors a request whose
        generation matches the run it just started.
        """
        request = {
            "slot_id": slot_id,
            "signal": signal_name,
            "run_generation": run_generation,
            "requested_at_ms": int(time.time() * 1000),
            "requested_by": "operator",
        }
        self.kills_dir.mkdir(parents=True, exist_ok=True)
        self._kill_path(slot_id).write_text(json.dumps(request), encoding="utf-8")
        return request

    def _terminal_kill_result(self, slot: dict) -> dict:
        receipt = self._last_receipt(slot, "task.termination")
        return {
            "slot_id": slot["slot_id"],
            "state": slot["state"],
            "kill_signal": "operator"
            if receipt and receipt.get("body", {}).get("kill_signal")
            else None,
            "receipt_id": receipt.get("receipt_id") if receipt else None,
            "exec_active": False,
        }

    def _kill_live_run(
        self, slot_id: str, run: dict, signal_name: str, wait_s: float
    ) -> dict:
        """Signal a live run and wait for its terminal receipt.

        The request stays on disk if the run does not finish within `wait_s`
        (bound to the run generation) so `exec_` consumes it when the run
        ends — a kill never seals a run that is still in flight.
        """
        generation = run.get("run_generation")
        self._write_kill_request(slot_id, signal_name, generation)
        self._signal_run(run, signal_name)

        def finished():
            fresh = self.registry.get_slot(slot_id)
            if fresh and fresh["state"] == "terminated":
                receipt = self._last_receipt(fresh, "task.termination")
                return {
                    "slot_id": slot_id,
                    "state": "terminated",
                    "kill_signal": "operator",
                    "receipt_id": receipt.get("receipt_id") if receipt else None,
                    "exec_active": True,
                }
            return None

        total_deadline = time.time() + wait_s
        grace_deadline = time.time() + min(1.0, max(wait_s, 0.0))
        result = None
        while time.time() < grace_deadline and result is None:
            result = finished()
            if result is None:
                time.sleep(0.05)
        if result is None:
            self._signal_run(run, "SIGKILL")
            while time.time() < total_deadline and result is None:
                result = finished()
                if result is None:
                    time.sleep(0.05)
        if result is not None:
            return result
        return {
            "slot_id": slot_id,
            "state": (self.registry.get_slot(slot_id) or {}).get("state", "unknown"),
            "outcome": "deferred",
            "kill_signal": "operator",
            "receipt_id": None,
            "exec_active": True,
            "hint": "run did not reach a terminal receipt within wait_s; the kill request is bound to the run generation and will be consumed when the run ends",
        }

    @staticmethod
    def _pid_alive(pid: int | None) -> bool:
        if not pid:
            return False
        try:
            os.kill(int(pid), 0)
            return True
        except (ProcessLookupError, PermissionError, ValueError, TypeError):
            return False

    def _signal_run(self, run: dict, signal_name: str) -> None:
        unit = run.get("unit")
        if unit:
            subprocess.run(
                ["systemctl", "--user", "kill", "--kill-whom=all", "-s", signal_name, unit],
                capture_output=True,
            )
            return
        sig = getattr(signal_mod, signal_name)
        pgid, pid = run.get("pgid"), run.get("pid")
        try:
            if pgid:
                os.killpg(int(pgid), sig)
            elif pid:
                os.kill(int(pid), sig)
        except (ProcessLookupError, PermissionError, ValueError, TypeError):
            pass

    # -- receipt emission -------------------------------------------------
    def _chain(self, slot: dict) -> TaskChain:
        chain = self._chains.get(slot["slot_id"])
        if chain is not None:
            return chain
        task_id = slot.get("task_id")
        if task_id:
            path = self.receipts_dir / f"{task_id}.json"
            if path.exists():
                bundle = json.loads(path.read_text(encoding="utf-8"))
                chain = TaskChain(task_id=task_id)
                chain.receipts = bundle.get("receipts", [])
                self._chains[slot["slot_id"]] = chain
                return chain
        chain = TaskChain(task_id=task_id)
        self._chains[slot["slot_id"]] = chain
        return chain

    def _emit(self, slot: dict, record_type: str, body: dict) -> dict:
        chain = self._chain(slot)
        receipt = chain.add(record_type, "gate", self.gate_did, self.gate_key, body)
        path = self.receipts_dir / f"{chain.task_id}.json"
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text(
                json.dumps(chain.bundle(), indent=2, sort_keys=False) + "\n",
                encoding="utf-8",
            )
            os.replace(tmp, path)
        except OSError as exc:
            chain.receipts.pop()
            raise EmitterError(f"receipt emitter unavailable: {exc}") from exc
        return receipt

    def task_id_for(self, slot_id: str) -> str | None:
        chain = self._chains.get(slot_id)
        return chain.task_id if chain else None

    def receipt(self, task_id: str) -> dict:
        return json.loads((self.receipts_dir / f"{task_id}.json").read_text(encoding="utf-8"))

    def _last_receipt(self, slot: dict, record_type: str) -> dict | None:
        task_id = slot.get("task_id") or self.task_id_for(slot["slot_id"])
        if not task_id:
            return None
        path = self.receipts_dir / f"{task_id}.json"
        if not path.exists():
            return None
        bundle = json.loads(path.read_text(encoding="utf-8"))
        for receipt in reversed(bundle.get("receipts", [])):
            if receipt.get("type") == record_type:
                return receipt
        return None

    def _termination_body(
        self,
        slot: dict,
        reason: str,
        kill_signal: str | None = None,
        killed_by: str | None = None,
        latency_ms: int | None = None,
    ) -> dict:
        quotas = slot.get("quotas", {})
        body = {
            "reason": reason,
            "limits_at_stop": {
                "cpu_ms": quotas.get("cpu_ms", 0),
                "wall_ms": quotas.get("wall_ms", 0),
                "spend_minor": 0,
                "currency": "USD",
            },
            "remaining": {
                "cpu_ms": 0,
                "wall_ms": max(slot.get("expires_at", now_epoch()) - now_epoch(), 0) * 1000,
                "spend_minor": 0,
                "currency": "USD",
            },
        }
        if kill_signal:
            body["kill_signal"] = kill_signal
        if killed_by:
            body["killed_by"] = killed_by
        if latency_ms is not None:
            body["operator_kill_latency_ms"] = latency_ms
        last = self._last_exec.get(slot["slot_id"])
        if last is not None:
            body["observed"] = {"exit": last.exit_code, "stdout_hash": last.stdout_hash}
        return body

    # -- lifecycle --------------------------------------------------------
    def pass_(
        self,
        tenant_id: str,
        agent_did: str,
        minutes: int = 90,
        slot_class: str = "small",
        spend_cap: dict | None = None,
        principal_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        if idempotency_key:
            cached = self.registry.recall(f"pass:{idempotency_key}")
            if cached:
                return cached
        tenant = self.registry.get_tenant(tenant_id)
        if tenant is None:
            raise KeyError(f"unknown tenant {tenant_id}")
        if slot_class not in SLOT_CLASSES:
            raise ValueError(f"unknown slot class {slot_class}")

        quotas = dict(SLOT_CLASSES[slot_class])
        quotas["wall_ms"] = minutes * 60000
        now = now_epoch()
        expires_at = now + minutes * 60
        slot_id = "slot-" + uuid.uuid4().hex[:12]
        pass_id = "pass-" + uuid.uuid4().hex[:12]
        jti = str(records.uuid7())

        claims = {
            "iss": f"gate:{self.gate_id}",
            "sub": agent_did,
            "aud": GATE_CLASS,
            "mandala": {"class": GATE_CLASS, "slot_class": slot_class, "quotas": quotas},
            "budget": spend_cap or {"minor": 0, "currency": "USD"},
            "policy_version": self.policy_version,
            "exp": expires_at,
            "jti": jti,
        }
        token = issue_pass(self.gate_did, self.gate_key, claims)

        body = {
            "gate_id": self.gate_id,
            "mandala_class": GATE_CLASS,
            "quotas": quotas,
            "expires_at": rfc3339(expires_at),
            "policy_version": self.policy_version,
            "mandate_ref": sha256_prefixed(f"mandate:{pass_id}".encode()),
            "agent_id": agent_did,
        }
        if spend_cap:
            body["spend_cap"] = spend_cap

        slot = dict(
            Slot(
                slot_id=slot_id,
                tenant_id=tenant_id,
                state="placed",
                slot_class=slot_class,
                quotas=quotas,
                created_at=now,
                expires_at=expires_at,
                pass_id=pass_id,
            ).__dict__
        )
        receipt = self._emit(slot, "session.pass.created", body)
        slot["task_id"] = self.task_id_for(slot_id)
        self.registry.put_slot(slot)
        self.registry.put_pass(
            {
                "pass_id": pass_id,
                "slot_id": slot_id,
                "agent_id": agent_did,
                "principal_id": principal_id,
                "expires_at": expires_at,
                "spend_cap": spend_cap,
                "jti": jti,
            }
        )
        (self.workspaces_dir / slot_id).mkdir(parents=True, exist_ok=True)
        result = {
            "pass_id": pass_id,
            "slot_id": slot_id,
            "endpoint": f"gate://{self.gate_id}/{slot_id}",
            "token": token,
            "quotas": quotas,
            "expires_at": rfc3339(expires_at),
            "receipt_id": receipt["receipt_id"],
        }
        if idempotency_key:
            self.registry.remember(f"pass:{idempotency_key}", result)
        return result

    def _authorized_slot(self, tenant_id: str, slot_id: str) -> dict:
        slot = self.registry.get_slot(slot_id)
        if slot is None:
            raise KeyError(f"unknown slot {slot_id}")
        if slot["tenant_id"] != tenant_id:
            raise PermissionError("cross-tenant access denied")
        return slot

    def exec_(
        self,
        tenant_id: str,
        slot_id: str,
        payload_ref: str,
        idempotency_key: str | None = None,
    ) -> dict:
        if idempotency_key:
            cached = self.registry.recall(f"exec:{idempotency_key}")
            if cached:
                return cached
        slot = self._authorized_slot(tenant_id, slot_id)
        if self._expire_if_needed(slot):
            raise ValueError("slot is expired")
        if slot["state"] in BLOCKED_STATES:
            raise ValueError(f"slot is {slot['state']}")
        previous_state = slot["state"]

        # Atomic start (issue #1): reserve the slot with a run generation
        # before any receipt or side effect, so a concurrent kill/expiry can
        # never seal a terminal state and then watch a process start. The
        # expiry predicate is part of the same transaction, so a slot that
        # expires between the read above and this CAS cannot start either.
        generation = int(slot.get("run_generation") or 0) + 1
        started = self.registry.cas_slot(
            slot_id,
            PRE_START_STATES,
            {
                "state": STARTING_STATE,
                "run_generation": generation,
                "starting_at_ms": int(time.time() * 1000),
            },
            require=lambda s: s.get("expires_at", 0) > now_epoch(),
        )
        if started is None:
            fresh = self.registry.get_slot(slot_id) or slot
            raise ValueError(
                f"start rejected: slot is {fresh['state']} — no process started"
            )
        slot = started

        try:
            decision = self._emit(
                slot,
                "task.decision",
                {
                    "action": "mandala.exec",
                    "action_args_hash": sha256_prefixed(payload_ref.encode()),
                    "model": {"provider": "gate", "id": "sandbox"},
                    "input_provenance": {
                        "policy_id": "gate.egress.default",
                        "allowed_sources": ["gate"],
                        "observed_sources_hash": sha256_prefixed(b"gate"),
                    },
                    "decision": "allow",
                    "policy_version": self.policy_version,
                },
            )
        except EmitterError:
            # No receipt, no start: release the reservation so the slot is not
            # wedged in `starting` (fail-closed but recoverable).
            self.registry.cas_slot(
                slot_id, (STARTING_STATE,), {"state": previous_state}
            )
            raise

        def on_spawn(pid: int, pgid: int, unit: str | None):
            self._journal_run(slot_id, pid, pgid, unit, generation)

        run_slot = dict(slot)
        run_slot["workspace"] = str(self.workspaces_dir / slot_id)
        try:
            result = self.runner.run(run_slot, payload_ref, on_spawn=on_spawn)
        except Exception:
            # The runner failed before any process of record exists; release
            # the reservation so the slot can be retried.
            if self.active_run(slot_id) is None:
                self.registry.cas_slot(
                    slot_id, (STARTING_STATE,), {"state": previous_state}
                )
            raise
        self._last_exec[slot_id] = result
        self._run_path(slot_id).unlink(missing_ok=True)

        execution = self._emit(
            slot,
            "task.execution",
            {
                "tool_calls": [
                    {
                        "name": "mandala.exec",
                        "args_hash": sha256_prefixed(payload_ref.encode()),
                        "result_hash": result.stdout_hash,
                    }
                ],
                "egress": result.egress or [{"destination": "none", "bytes": 0, "allowed": True}],
                "resources": result.resources,
                "sandbox_class": getattr(self.runner, "sandbox_class", "bwrap-landlock"),
            },
        )

        kill_request = self._consume_kill_request(slot_id)
        if kill_request is not None and kill_request.get("run_generation") not in (
            None,
            generation,
        ):
            # A request bound to an older run must never terminate this one —
            # a late start cannot consume an old request (issue #1).
            kill_request = None
        response = {
            "slot_id": slot_id,
            "exit": result.exit_code,
            "stdout_hash": result.stdout_hash,
            "receipt_ids": [decision["receipt_id"], execution["receipt_id"]],
        }
        if result.stderr_hash:
            response["stderr_hash"] = result.stderr_hash

        termination = None
        final_state = "terminated"
        fresh_slot = self.registry.get_slot(slot_id) or slot
        if kill_request is not None:
            latency_ms = max(int(time.time() * 1000) - int(kill_request.get("requested_at_ms", 0)), 0)
            termination = self._emit(
                slot,
                "task.termination",
                self._termination_body(
                    slot, "killed", kill_signal="operator", latency_ms=latency_ms
                ),
            )
            response["kill_signal"] = "operator"
            response["operator_kill_latency_ms"] = latency_ms
        elif result.killed_by:
            termination = self._emit(
                slot,
                "task.termination",
                self._termination_body(slot, "quota", kill_signal="quota", killed_by=result.killed_by),
            )
            response["kill_signal"] = "quota"
            response["reason"] = "quota"
        elif int(fresh_slot.get("expires_at", 0)) <= now_epoch():
            # Expiry landed while the run was live; the seal is deferred to
            # here so receipts stay monotonic (decision → execution →
            # termination) instead of sealing mid-run.
            termination = self._emit(
                slot,
                "task.termination",
                self._termination_body(slot, "time_expired"),
            )
            response["reason"] = "time_expired"
            final_state = "expired"

        if termination is not None:
            response["receipt_ids"].append(termination["receipt_id"])
            self.registry.cas_slot(
                slot_id, (STARTING_STATE,), {"state": final_state}
            )
        else:
            self.registry.cas_slot(slot_id, (STARTING_STATE,), {"state": "active"})

        if idempotency_key:
            self.registry.remember(f"exec:{idempotency_key}", response)
        return response

    def settle(
        self,
        tenant_id: str,
        slot_id: str,
        rail: str,
        rail_ref: str,
        minor: int,
        currency: str = "USD",
        gated_on_delivery: bool = True,
    ) -> dict:
        slot = self._authorized_slot(tenant_id, slot_id)
        pass_record = self.registry.get_pass(slot["pass_id"]) or {}
        cap = pass_record.get("spend_cap")
        if cap and (currency != cap.get("currency") or minor > int(cap.get("minor", 0))):
            raise ValueError(f"spend cap exceeded: {minor} {currency} > {cap}")

        if gated_on_delivery:
            last = self._last_exec.get(slot_id)
            self._emit(
                slot,
                "delivery.attestation",
                {
                    "request_hash": sha256_prefixed(f"request:{slot_id}".encode()),
                    "response_hash": last.stdout_hash
                    if last
                    else sha256_prefixed(b"none"),
                    "counterparty": {"id": self.gate_did},
                    "spec_ref": "continuity-receipt/0.1",
                },
            )
        return self._emit(
            slot,
            "settlement",
            {
                "rail": rail,
                "rail_ref": rail_ref,
                "amount": {"minor": minor, "currency": currency},
                "gated_on_delivery": gated_on_delivery,
                "settled_at": rfc3339(now_epoch()),
            },
        )

    def terminate(
        self,
        tenant_id: str,
        slot_id: str,
        reason: str = "completed",
        kill_signal: str | None = None,
    ) -> dict:
        slot = self._authorized_slot(tenant_id, slot_id)
        # Reserve the terminal transition atomically (issue #1): an in-flight
        # start must never be sealed, and an idle slot must not be sealed
        # between the read and the write.
        reserved = self.registry.cas_slot(
            slot_id, IDLE_SEALABLE_STATES, {"state": TERMINATING_STATE}
        )
        if reserved is None:
            fresh = self.registry.get_slot(slot_id) or slot
            if fresh["state"] in TERMINAL_STATES:
                receipt = self._last_receipt(fresh, "task.termination")
                return {
                    "slot_id": slot_id,
                    "task_id": fresh.get("task_id") or self.task_id_for(slot_id),
                    "receipt_id": receipt.get("receipt_id") if receipt else None,
                }
            raise ValueError(
                f"terminate rejected: slot is {fresh['state']} — a start is in flight"
            )
        receipt = self._emit(
            reserved,
            "task.termination",
            self._termination_body(reserved, reason, kill_signal=kill_signal),
        )
        self.registry.cas_slot(slot_id, (TERMINATING_STATE,), {"state": "terminated"})
        return {"slot_id": slot_id, "task_id": self.task_id_for(slot_id), "receipt_id": receipt["receipt_id"]}

    def kill(self, tenant_id: str, slot_id: str, signal_name: str = "SIGTERM", wait_s: float = 5.0) -> dict:
        """Operator kill: terminates a live run within `wait_s` seconds (escalates to SIGKILL)."""
        slot = self._authorized_slot(tenant_id, slot_id)
        if self._expire_if_needed(slot):
            raise ValueError("slot is expired")
        if slot["state"] in TERMINAL_STATES:
            raise ValueError(f"slot is {slot['state']}")

        for _ in range(2):
            run = self.active_run(slot_id)
            if run and self._pid_alive(run.get("pid")):
                return self._kill_live_run(slot_id, run, signal_name, wait_s)

            if slot["state"] == STARTING_STATE:
                # Start in flight, no pid journaled yet (issue #1): bind the
                # request to this generation and wait for the journal or the
                # run to finish. Never seal mid-start.
                generation = int(slot.get("run_generation") or 0)
                self._write_kill_request(slot_id, signal_name, generation)
                deadline = time.time() + wait_s
                while time.time() < deadline:
                    run = self.active_run(slot_id)
                    if run and self._pid_alive(run.get("pid")):
                        return self._kill_live_run(
                            slot_id, run, signal_name, max(deadline - time.time(), 0.1)
                        )
                    fresh = self.registry.get_slot(slot_id) or slot
                    if fresh["state"] in TERMINAL_STATES:
                        return self._terminal_kill_result(fresh)
                    if fresh["state"] != STARTING_STATE:
                        slot = fresh
                        break
                    time.sleep(0.05)
                else:
                    fresh = self.registry.get_slot(slot_id) or slot
                    if fresh["state"] in TERMINAL_STATES:
                        return self._terminal_kill_result(fresh)
                    return {
                        "slot_id": slot_id,
                        "state": fresh["state"],
                        "outcome": "deferred",
                        "kill_signal": "operator",
                        "receipt_id": None,
                        "exec_active": False,
                        "hint": f"start in flight (generation {generation}); the kill request is bound to that generation and will be consumed when the run starts",
                    }
                continue

            # Idle slot: reserve the terminal transition atomically so a
            # concurrent start cannot slip between the read and the seal.
            reserved = self.registry.cas_slot(
                slot_id, IDLE_SEALABLE_STATES, {"state": TERMINATING_STATE}
            )
            if reserved is None:
                slot = self.registry.get_slot(slot_id) or slot
                if slot["state"] in TERMINAL_STATES:
                    return self._terminal_kill_result(slot)
                continue  # a start raced in; the next iteration handles it
            receipt = self._emit(
                reserved,
                "task.termination",
                self._termination_body(reserved, "killed", kill_signal="operator"),
            )
            self.registry.cas_slot(
                slot_id, (TERMINATING_STATE,), {"state": "terminated"}
            )
            return {
                "slot_id": slot_id,
                "state": "terminated",
                "kill_signal": "operator",
                "receipt_id": receipt["receipt_id"],
                "exec_active": False,
            }

        fresh = self.registry.get_slot(slot_id) or slot
        if fresh["state"] in TERMINAL_STATES:
            return self._terminal_kill_result(fresh)
        return {
            "slot_id": slot_id,
            "state": fresh["state"],
            "outcome": "unknown",
            "kill_signal": "operator",
            "receipt_id": None,
            "exec_active": False,
            "hint": "kill could not be bound to a run or an idle slot; retry",
        }

    def snapshot(self, tenant_id: str, slot_id: str) -> dict:
        """Filesystem snapshot of the slot workspace (gate-lite: no store image)."""
        slot = self._authorized_slot(tenant_id, slot_id)
        if self._expire_if_needed(slot):
            raise ValueError("slot is expired")
        if slot["state"] in TERMINAL_STATES:
            raise ValueError(f"slot is {slot['state']}")
        workspace = self.workspaces_dir / slot_id
        workspace.mkdir(parents=True, exist_ok=True)
        snapshot_id = "snap-" + uuid.uuid4().hex[:12]
        archive_dir = self.snapshots_dir / slot_id
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / f"{snapshot_id}.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tar:
            for child in sorted(workspace.iterdir()):
                tar.add(child, arcname=child.name, recursive=True)
        payload = archive_path.read_bytes()
        digest = sha256_prefixed(payload)
        workspace_hash = tree_hash(workspace)
        receipt = self._emit(
            slot,
            "delivery.attestation",
            {
                "request_hash": sha256_prefixed(f"snapshot:{slot_id}:{snapshot_id}".encode()),
                "response_hash": digest,
                "counterparty": {"id": self.gate_did},
                "spec_ref": "continuity-receipt/0.1",
                "artifact": {
                    "snapshot_id": snapshot_id,
                    "kind": "filesystem-tar.gz",
                    "bytes": len(payload),
                    "sha256": digest,
                },
            },
        )
        self.registry.put_snapshot(
            {
                "snapshot_id": snapshot_id,
                "slot_id": slot_id,
                "tenant_id": tenant_id,
                "artifact": str(archive_path),
                "sha256": digest,
                "bytes": len(payload),
                "tree_hash": workspace_hash,
                "created_at": now_epoch(),
            }
        )
        fresh = self.registry.get_slot(slot_id) or slot
        if fresh["state"] not in TERMINAL_STATES:
            fresh["state"] = "frozen"
            self.registry.put_slot(fresh)
        return {
            "slot_id": slot_id,
            "snapshot_id": snapshot_id,
            "receipt_id": receipt["receipt_id"],
            "state": fresh["state"],
            "tree_hash": workspace_hash,
            "artifact": {"path": str(archive_path), "sha256": digest, "bytes": len(payload)},
        }

    def restore(self, tenant_id: str, slot_id: str, snapshot_id: str) -> dict:
        """Materialize a snapshot into a placed slot (G7 lane; filesystem only)."""
        slot = self._authorized_slot(tenant_id, slot_id)
        if self._expire_if_needed(slot):
            raise ValueError("slot is expired")
        if slot["state"] != "placed":
            raise ValueError(f"slot is {slot['state']}; restore needs a placed slot")
        record = self.registry.get_snapshot(snapshot_id)
        if record is None:
            raise KeyError(f"unknown snapshot {snapshot_id}")
        if record["tenant_id"] != tenant_id:
            raise PermissionError("cross-tenant snapshot access denied")
        archive = Path(record["artifact"])
        if not archive.exists():
            raise KeyError(f"snapshot artifact missing: {archive}")
        payload = archive.read_bytes()
        digest = sha256_prefixed(payload)
        if digest != record["sha256"]:
            raise ValueError("snapshot integrity check failed")

        workspace = self.workspaces_dir / slot_id
        if workspace.exists() and any(workspace.iterdir()):
            raise ValueError("workspace is not empty")
        workspace.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as tar:
            _safe_extract(tar, workspace)

        restored = tree_hash(workspace)
        receipt = self._emit(
            slot,
            "delivery.attestation",
            {
                "request_hash": record["sha256"],
                "response_hash": restored,
                "counterparty": {"id": self.gate_did},
                "spec_ref": "continuity-receipt/0.1",
                "artifact": {
                    "snapshot_id": snapshot_id,
                    "kind": "filesystem-restore",
                    "sha256": record["sha256"],
                    "restored_into": slot_id,
                },
            },
        )
        return {
            "slot_id": slot_id,
            "snapshot_id": snapshot_id,
            "workspace": str(workspace),
            "restored_hash": restored,
            "receipt_id": receipt["receipt_id"],
        }

    def _expire_if_needed(self, slot: dict) -> bool:
        if slot["state"] in TERMINAL_STATES or slot.get("expires_at", 0) > now_epoch():
            return False
        if slot["state"] in (STARTING_STATE, TERMINATING_STATE):
            # A start/terminate is in flight; sealing here would break receipt
            # monotonicity and could seal before a process starts (issue #1).
            # exec_ applies the expiry after the run, as a termination receipt
            # that follows task.execution.
            return False
        if self.active_run(slot["slot_id"]):
            # Live run: expiry is applied by exec_ after execution.
            return False
        reserved = self.registry.cas_slot(
            slot["slot_id"], IDLE_SEALABLE_STATES, {"state": TERMINATING_STATE}
        )
        if reserved is None:
            return False
        self._emit(
            reserved,
            "task.termination",
            self._termination_body(reserved, "time_expired"),
        )
        self.registry.cas_slot(
            slot["slot_id"], (TERMINATING_STATE,), {"state": "expired"}
        )
        return True

    def sweep_expired(self, tenant_id: str | None = None) -> dict:
        """Seal every past-expiry slot with a time_expired termination receipt."""
        sealed = []
        for slot in self.registry.all_slots(tenant_id):
            if slot["state"] in TERMINAL_STATES:
                continue
            if slot["state"] in (STARTING_STATE, TERMINATING_STATE):
                # In-flight transitions seal themselves; never mid-start.
                continue
            if self.active_run(slot["slot_id"]):
                # Live run: exec_ applies the expiry after execution.
                continue
            if self._expire_if_needed(slot):
                sealed.append(
                    {
                        "slot_id": slot["slot_id"],
                        "tenant_id": slot["tenant_id"],
                        "receipt_id": self._last_receipt(slot, "task.termination").get("receipt_id"),
                    }
                )
        return {"expired": sealed, "count": len(sealed)}

    def status(self, tenant_id: str, slot_id: str) -> dict:
        slot = self._authorized_slot(tenant_id, slot_id)
        return {"slot": slot}

    def list_(self, tenant_id: str) -> list[dict]:
        return self.registry.slots_for(tenant_id)
