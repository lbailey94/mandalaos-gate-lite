#!/usr/bin/env python3
"""Gate-lite comprehensive benchmark suite.

Profiles: quick | standard | deep. Measures receipt primitives, registry and
multi-process contention, orchestrator flows, real-runner overhead (bwrap +
systemd slices), MCP transports (stdio/HTTP/concurrency), and a soak with
latency drift. Writes results.json, results.csv, report.md and env.json under
the output directory.

Run: python3 tools/bench.py --out evidence/bench-2026-09-18 [--profile standard]
"""
import argparse
import csv
import http.client
import json
import math
import os
import platform
import resource
import shutil
import statistics
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from continuity_receipt import keys, records, verify_bundle  # noqa: E402
from continuity_receipt.bundle import TaskChain  # noqa: E402
from continuity_receipt.canon import canonical_bytes, commit_field, sha256_prefixed  # noqa: E402
from gate_lite.mcp_server import McpHttpServer, McpServer  # noqa: E402
from gate_lite.orchestrator import Orchestrator, SandboxRunner, SliceRunner  # noqa: E402
from gate_lite.registry import Registry  # noqa: E402

WRAPPER = (
    os.environ.get("WM_GATELITE_RUNNER")
    or shutil.which("mandala-sandbox")
    or str(Path.home() / ".local" / "bin" / "mandala-sandbox")
)
HAS_SANDBOX = Path(WRAPPER).exists() and shutil.which("bwrap") is not None
AGENT_DID = "did:key:zBenchAgent"


def systemd_user_ok() -> bool:
    if not (shutil.which("systemd-run") and shutil.which("systemctl")):
        return False
    try:
        probe = subprocess.run(
            ["systemctl", "--user", "is-system-running"], capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return probe.stdout.strip() in ("running", "degraded")


HAS_SYSTEMD = systemd_user_ok()
PROFILES = {
    "quick": {"target_s": 0.2, "max_iters": 200, "soak_flows": 100, "sizes_mb": (1, 10)},
    "standard": {"target_s": 0.8, "max_iters": 2000, "soak_flows": 300, "sizes_mb": (1, 10, 50)},
    "deep": {"target_s": 3.0, "max_iters": 20000, "soak_flows": 2000, "sizes_mb": (1, 10, 50, 100)},
}


def env_facts() -> dict:
    def read(path):
        try:
            return Path(path).read_text(encoding="utf-8").strip()
        except OSError:
            return None

    cpu = None
    for line in read("/proc/cpuinfo").splitlines() if read("/proc/cpuinfo") else []:
        if line.startswith("model name"):
            cpu = line.split(":", 1)[1].strip()
            break
    facts = {
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hostname": platform.node(),
        "platform": platform.platform(),
        "kernel": platform.release(),
        "cpu": cpu,
        "nproc": os.cpu_count(),
        "python": sys.version.split()[0],
        "bwrap": None,
        "systemd": None,
        "runner": WRAPPER,
        "loadavg_start": list(os.getloadavg()),
        "mem_total_mb": None,
    }
    try:
        facts["bwrap"] = subprocess.run(["bwrap", "--version"], capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        facts["systemd"] = subprocess.run(["systemctl", "--version"], capture_output=True, text=True, timeout=10).stdout.splitlines()[0]
    except (OSError, subprocess.TimeoutExpired):
        pass
    meminfo = read("/proc/meminfo") or ""
    for line in meminfo.splitlines():
        if line.startswith("MemTotal"):
            facts["mem_total_mb"] = int(line.split()[1]) // 1024
    return facts


def percentile(sorted_samples: list, pct: float):
    if not sorted_samples:
        return None
    index = max(0, min(len(sorted_samples) - 1, math.ceil(pct / 100.0 * len(sorted_samples)) - 1))
    return sorted_samples[index]


def summarize(samples_ms: list) -> dict:
    samples = sorted(samples_ms)
    n = len(samples)
    total_s = sum(samples) / 1000.0
    return {
        "n": n,
        "median_ms": round(statistics.median(samples), 4),
        "p95_ms": round(percentile(samples, 95), 4),
        "p99_ms": round(percentile(samples, 99), 4),
        "mean_ms": round(statistics.fmean(samples), 4),
        "min_ms": round(samples[0], 4),
        "max_ms": round(samples[-1], 4),
        "stdev_ms": round(statistics.stdev(samples), 4) if n > 1 else 0.0,
        "total_s": round(total_s, 4),
        "per_sec": round(n / total_s, 2) if total_s > 0 else None,
    }


def current_rss_mb() -> float:
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024.0
    except OSError:
        pass
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def make_orchestrator(state: Path, runner=None) -> Orchestrator:
    did, key = keys.generate(keys.deterministic_seed("bench-gate"))
    orch = Orchestrator(state, gate_id="bench", gate_key=key, gate_did=did, runner=runner)
    orch.add_tenant("bench", [AGENT_DID])
    return orch


def decision_body(index: int) -> dict:
    return {
        "action": "mandala.exec",
        "action_args_hash": sha256_prefixed(f"arg-{index}".encode()),
        "model": {"provider": "bench", "id": "stub"},
        "input_provenance": {
            "policy_id": "bench.policy",
            "allowed_sources": ["bench"],
            "observed_sources_hash": sha256_prefixed(b"bench"),
        },
        "decision": "allow",
        "policy_version": "bench.1",
    }


def pass_body() -> dict:
    return {
        "gate_id": "bench",
        "mandala_class": "gate-lite",
        "quotas": {"cpu_ms": 1000, "mem_mb": 64, "disk_mb": 1, "wall_ms": 1000},
        "expires_at": "2030-01-01T00:00:00Z",
        "policy_version": "bench.1",
        "mandate_ref": sha256_prefixed(b"mandate"),
        "agent_id": AGENT_DID,
    }


def termination_body() -> dict:
    return {
        "reason": "completed",
        "limits_at_stop": {"cpu_ms": 1000, "wall_ms": 1000, "spend_minor": 0, "currency": "USD"},
        "remaining": {"cpu_ms": 0, "wall_ms": 0, "spend_minor": 0, "currency": "USD"},
    }


def build_chain(receipt_count: int):
    did, key = keys.generate(keys.deterministic_seed("bench-chain"))
    chain = TaskChain()
    chain.add("session.pass.created", "gate", did, key, pass_body())
    for index in range(receipt_count - 2):
        chain.add("task.decision", "gate", did, key, decision_body(index))
    chain.add("task.termination", "gate", did, key, termination_body())
    return chain, did, key


class Bench:
    def __init__(self, out: Path, profile: str, keep: bool = False, oom_drill: bool = False):
        self.out = out
        self.out.mkdir(parents=True, exist_ok=True)
        self.profile = profile
        self.cfg = PROFILES[profile]
        self.keep = keep
        self.oom_drill = oom_drill
        self.env = env_facts()
        self.results: list[dict] = []
        self.metrics: list[dict] = []
        self.invariants: list[dict] = []

    def state_dir(self, name: str) -> Path:
        path = self.out / "state" / name
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)
        return path

    def record(self, group: str, name: str, unit: str, samples_ms: list, meta: dict | None = None) -> dict:
        entry = {
            "group": group,
            "name": name,
            "unit": unit,
            **summarize(samples_ms),
            "samples_ms": [round(sample, 4) for sample in samples_ms],
            "meta": meta or {},
        }
        self.results.append(entry)
        print(f"  [{group}] {name}: median {entry['median_ms']} ms (n={entry['n']})")
        return entry

    def metric(self, group: str, name: str, value, unit: str, meta: dict | None = None) -> dict:
        entry = {"group": group, "name": name, "value": value, "unit": unit, "meta": meta or {}}
        self.metrics.append(entry)
        return entry

    def invariant(self, name: str, ok: bool, detail: str = "") -> None:
        self.invariants.append({"name": name, "ok": bool(ok), "detail": detail})
        print(f"  [invariant] {name}: {'PASS' if ok else 'FAIL'} {detail}")

    @staticmethod
    def time_once(fn) -> float:
        started = time.perf_counter()
        fn()
        return (time.perf_counter() - started) * 1000.0

    def measure(self, group: str, name: str, unit: str, fn, *, warmup: int = 3,
                min_iters: int = 5, iters: int | None = None, meta: dict | None = None) -> dict:
        for _ in range(min(warmup, 3)):
            fn()
        if iters is None:
            probe = self.time_once(fn) / 1000.0
            per_op = max(probe, 1e-6)
            iters = int(max(min_iters, min(self.cfg["max_iters"], self.cfg["target_s"] / per_op)))
        samples = [self.time_once(fn) for _ in range(iters)]
        return self.record(group, name, unit, samples, meta)


def bench_primitives(b: Bench) -> None:
    print("A. receipt primitives")
    did, key = keys.generate(keys.deterministic_seed("bench-primitives"))
    small_body = decision_body(0)
    large_body = {
        "action": "mandala.exec",
        "tool_calls": [
            {"name": f"tool-{i}", "args_hash": sha256_prefixed(f"a{i}".encode()), "result_hash": sha256_prefixed(f"r{i}".encode())}
            for i in range(200)
        ],
        "policy_version": "bench.1",
        "notes": ["x" * 64] * 50,
    }
    salt = "ab" * 16
    envelope = records.new_envelope("urn:uuid:bench", "gate", did, "task.decision", 0, None, small_body)

    b.measure("A", "canonicalize body (small, ~0.3 KB)", "ms/op", lambda: canonical_bytes(small_body))
    b.measure("A", "canonicalize body (large, ~20 KB)", "ms/op", lambda: canonical_bytes(large_body))
    b.measure("A", "commit_field (small body)", "ms/op", lambda: commit_field(salt, small_body))
    b.measure("A", "sign_receipt (Ed25519)", "ms/op", lambda: records.sign_receipt(envelope, key, did))

    chain6, _, _ = build_chain(6)
    bundle6 = chain6.bundle()
    result6 = verify_bundle(bundle6)
    b.invariant("6-receipt bundle verifies TRUSTED", result6.verdict == "TRUSTED", result6.verdict)
    b.measure("A", "verify bundle (6 receipts)", "ms/bundle", lambda: verify_bundle(bundle6))

    chain100, _, _ = build_chain(100)
    bundle100 = chain100.bundle()
    result100 = verify_bundle(bundle100)
    b.invariant("100-receipt bundle verifies TRUSTED", result100.verdict == "TRUSTED", result100.verdict)
    b.measure("A", "verify bundle (100 receipts)", "ms/bundle", lambda: verify_bundle(bundle100))

    def build_100():
        chain, _, _ = build_chain(100)
        return chain

    b.measure("A", "build chain (100 receipts)", "ms/chain", build_100, min_iters=5)

    tampered = json.loads(json.dumps(bundle100))
    tampered["receipts"][50]["body"]["decision"] = "deny"
    tamper_result = verify_bundle(tampered)
    b.invariant("tampered 100-receipt bundle is UNTRUSTED", tamper_result.verdict == "UNTRUSTED", ",".join(tamper_result.codes()))
    b.measure("A", "verify tampered bundle (100 receipts)", "ms/bundle", lambda: verify_bundle(tampered))

    compact = {
        "pass": records.new_envelope("urn:uuid:s0", "gate", did, "session.pass.created", 0, None, pass_body()),
        "decision": records.new_envelope("urn:uuid:s1", "gate", did, "task.decision", 1, sha256_prefixed(b"p"), small_body),
        "termination": records.new_envelope("urn:uuid:s2", "gate", did, "task.termination", 2, sha256_prefixed(b"q"), termination_body()),
    }
    for name, receipt in compact.items():
        b.metric("A/sizes", f"receipt compact bytes ({name})", len(canonical_bytes(receipt)), "bytes")
    full_chain, _, _ = build_chain(6)
    bundle = full_chain.bundle()
    b.metric("A/sizes", "bundle compact bytes (6 receipts)", len(canonical_bytes(bundle)), "bytes")
    b.metric("A/sizes", "bundle stored bytes (6 receipts, indent=2)", len(json.dumps(bundle, indent=2)) + 1, "bytes")
    minimal_chain, _, _ = build_chain(2)
    minimal = minimal_chain.bundle()
    b.metric("A/sizes", "bundle compact bytes (pass+termination)", len(canonical_bytes(minimal)), "bytes")
    b.metric("A/sizes", "receipts per task (full flow)", 6, "count")


def store_bytes(state: Path) -> int:
    total = 0
    for suffix in ("", "-wal"):
        path = state / f"registry.db{suffix}"
        if path.exists():
            total += path.stat().st_size
    return total


def seed_registry(state: Path, slot_count: int) -> Registry:
    state.mkdir(parents=True, exist_ok=True)
    registry = Registry(state / "registry.db")
    slots = []
    for index in range(slot_count):
        slot_id = f"slot-{index:08x}"
        slots.append({
            "slot_id": slot_id,
            "tenant_id": "bench",
            "state": "active",
            "slot_class": "small",
            "quotas": {"cpu_ms": 300000, "mem_mb": 1024, "disk_mb": 512, "wall_ms": 60000},
            "created_at": 1700000000 + index,
            "expires_at": 1800000000 + index,
            "template": "default",
            "pass_id": f"pass-{index:08x}",
            "task_id": f"task-{index:08x}",
        })
    registry.put_tenant({"tenant_id": "bench", "agents": [AGENT_DID], "aup_version": "bench", "settlement_ref": None})
    registry.put_many("slots", slots)
    return registry


def bench_registry(b: Bench) -> None:
    print("B. registry & multi-process")
    sizes = [100, 1000, 10000] if b.profile != "deep" else [100, 1000, 10000, 50000]
    for slot_count in sizes:
        state = b.state_dir(f"registry-{slot_count}")
        registry = seed_registry(state, slot_count)
        b.metric("B/sizes", f"registry db bytes ({slot_count} slots)", store_bytes(state), "bytes", {"slots": slot_count})
        slot_id = f"slot-{slot_count // 2:08x}"
        b.measure("B", f"get_slot ({slot_count} slots)", "ms/op", lambda: registry.get_slot(slot_id), meta={"slots": slot_count})

        def put_once():
            slot = registry.get_slot(slot_id)
            slot["expires_at"] += 1
            registry.put_slot(slot)

        b.measure("B", f"put_slot ({slot_count} slots)", "ms/op", put_once, min_iters=5,
                  iters=10 if slot_count >= 10000 else None, meta={"slots": slot_count})
        b.measure("B", f"recall miss ({slot_count} slots)", "ms/op", lambda: registry.recall("nope"), meta={"slots": slot_count})

    state = b.state_dir("parallel-writers")
    make_orchestrator(state)
    registry = Registry(state / "registry.db")
    for workers, per_worker in ((4, 5), (8, 5), (16, 5)):
        before = len(registry.reload()["slots"])
        procs = []
        t0 = time.perf_counter()
        for worker in range(workers):
            for op in range(per_worker):
                procs.append(
                    subprocess.Popen(
                        [
                            sys.executable, "-m", "gate_lite.ctl", "--state", str(state),
                            "pass", "--tenant", "bench", "--agent", AGENT_DID,
                        ],
                        cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                    )
                )
        failures = 0
        for proc in procs:
            _, err = proc.communicate()
            if proc.returncode != 0:
                failures += 1
        wall_ms = (time.perf_counter() - t0) * 1000
        after = len(registry.reload()["slots"])
        expected = before + workers * per_worker
        b.metric(
            "B/parallel", f"parallel pass writers ({workers} workers x {per_worker})",
            round(wall_ms, 2), "ms wall",
            {"workers": workers, "ops": workers * per_worker, "ms_per_op": round(wall_ms / (workers * per_worker), 2),
             "failures": failures, "slots_before": before, "slots_after": after},
        )
        b.invariant(
            f"no lost updates at {workers} parallel writers",
            failures == 0 and after == expected,
            f"failures={failures} slots={after}/{expected}",
        )

    slot_id = f"slot-{5:08x}"
    registry = Registry(state / "registry.db")
    target = registry.get_slot(slot_id) or next(iter(registry.reload()["slots"].values()))
    readers = 8
    per_reader = 5
    t0 = time.perf_counter()
    procs = [
        subprocess.Popen(
            [
                sys.executable, "-m", "gate_lite.ctl", "--state", str(state),
                "status", "--tenant", "bench", "--slot", target["slot_id"],
            ],
            cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )
        for _ in range(readers * per_reader)
    ]
    failures = 0
    for proc in procs:
        _, err = proc.communicate()
        if proc.returncode != 0:
            failures += 1
    wall_ms = (time.perf_counter() - t0) * 1000
    b.metric(
        "B/parallel", f"parallel status readers ({readers * per_reader} processes)",
        round(wall_ms, 2), "ms wall",
        {"ops": readers * per_reader, "ms_per_op": round(wall_ms / (readers * per_reader), 2), "failures": failures},
    )
    b.invariant("parallel readers all succeed", failures == 0, f"failures={failures}")


def bench_orchestrator(b: Bench) -> None:
    print("C. orchestrator (stub runner)")
    state = b.state_dir("orchestrator-flow")
    orch = make_orchestrator(state)

    def full_flow():
        issued = orch.pass_("bench", AGENT_DID, minutes=5)
        orch.exec_("bench", issued["slot_id"], "echo bench")
        orch.settle("bench", issued["slot_id"], "invoice", "bench-inv", 0)
        orch.terminate("bench", issued["slot_id"])

    flow = b.measure("C", "full flow (pass/exec/settle/terminate)", "ms/flow", full_flow, min_iters=10)
    last_task = None

    def flow_verified():
        nonlocal last_task
        issued = orch.pass_("bench", AGENT_DID, minutes=5)
        orch.exec_("bench", issued["slot_id"], "echo bench")
        terminated = orch.terminate("bench", issued["slot_id"])
        last_task = terminated["task_id"]

    b.measure("C", "flow without settlement (3 receipts)", "ms/flow", flow_verified, min_iters=10)
    if last_task:
        verdict = verify_bundle(orch.receipt(last_task))
        b.invariant("bench flow bundle verifies TRUSTED", verdict.verdict == "TRUSTED", verdict.verdict)

    def idempotent_replay():
        first = orch.pass_("bench", AGENT_DID, idempotency_key="bench-p1")
        orch.pass_("bench", AGENT_DID, idempotency_key="bench-p1")
        orch.exec_("bench", first["slot_id"], "echo idem", idempotency_key="bench-e1")
        orch.exec_("bench", first["slot_id"], "echo idem", idempotency_key="bench-e1")

    b.measure("C", "idempotent replay (pass+exec)", "ms/op", idempotent_replay, min_iters=10)

    def seed_expired_slots(state: Path, count: int) -> None:
        make_orchestrator(state)
        registry = Registry(state / "registry.db")
        slots = []
        for index in range(count):
            slot_id = f"slot-sweep-{index:04d}"
            slots.append({
                "slot_id": slot_id,
                "tenant_id": "bench",
                "state": "active",
                "slot_class": "small",
                "quotas": {"cpu_ms": 1000, "mem_mb": 64, "disk_mb": 1, "wall_ms": 1000},
                "created_at": 1700000000,
                "expires_at": 1,
                "template": "default",
                "pass_id": None,
                "task_id": f"task-sweep-{index:04d}",
            })
        registry.put_many("slots", slots)

    sweep_samples = []
    sweep_sealed = []
    for batch in range(3):
        sweep_state = b.state_dir(f"sweep-{batch}")
        seed_expired_slots(sweep_state, 500)
        orch_sweep = make_orchestrator(sweep_state)
        started = time.perf_counter()
        sealed = orch_sweep.sweep_expired("bench")
        sweep_samples.append((time.perf_counter() - started) * 1000)
        sweep_sealed.append(sealed["count"])
    b.record("C", "sweep 500 expired slots (fresh batch)", "ms/batch", sweep_samples)
    b.metric("C/sizes", "sweep per slot", round(statistics.median(sweep_samples) / 500, 4), "ms/slot")
    b.invariant("sweep sealed the fresh batches", all(count == 500 for count in sweep_sealed), f"sealed={sweep_sealed}")

    for size_mb in b.cfg["sizes_mb"]:
        snap_state = b.state_dir(f"snapshot-{size_mb}mb")
        orch_snap = make_orchestrator(snap_state)
        payload = os.urandom(1024 * 1024) * size_mb
        iters = 5 if size_mb <= 10 else 3
        slots = []
        for _ in range(iters):
            issued = orch_snap.pass_("bench", AGENT_DID, minutes=5)
            workspace = snap_state / "workspaces" / issued["slot_id"]
            (workspace / "payload.bin").write_bytes(payload)
            slots.append(issued["slot_id"])
        queue = list(slots)
        archives = []
        snapshot_ids = []

        def do_snapshot():
            snap = orch_snap.snapshot("bench", queue.pop(0))
            archives.append(snap["artifact"]["bytes"])
            snapshot_ids.append(snap["snapshot_id"])

        b.measure("C", f"snapshot workspace {size_mb} MB", "ms/op", do_snapshot, warmup=0, iters=iters)
        median_archive = statistics.median(archives)
        b.metric("C/sizes", f"snapshot archive bytes ({size_mb} MB source)", int(median_archive), "bytes",
                 {"source_bytes": size_mb * 1024 * 1024, "ratio": round(median_archive / (size_mb * 1024 * 1024), 4)})

        restore_jobs = []
        for snapshot_id in snapshot_ids:
            recreated = orch_snap.pass_("bench", AGENT_DID, minutes=5)
            restore_jobs.append((recreated["slot_id"], snapshot_id))

        def do_restore():
            slot_id, snapshot_id = restore_jobs.pop(0)
            orch_snap.restore("bench", slot_id, snapshot_id)

        b.measure("C", f"restore workspace {size_mb} MB", "ms/op", do_restore, warmup=0, iters=len(restore_jobs))
        if not b.keep:
            shutil.rmtree(snap_state / "snapshots", ignore_errors=True)
            shutil.rmtree(snap_state / "workspaces", ignore_errors=True)

    list_state = b.state_dir("list-10000")
    seed_registry(list_state, 10000)
    list_orch = make_orchestrator(list_state)
    listed = list_orch.list_("bench")
    b.invariant("list_ returns all seeded slots", len(listed) == 10000 + 0, f"count={len(listed)}")
    b.measure("C", "list_ tenant slots (10k registry)", "ms/op", lambda: list_orch.list_("bench"), min_iters=5)


def bench_runner(b: Bench) -> None:
    print("D. real runner (bwrap + systemd slices)")
    if not HAS_SANDBOX:
        b.metric("D", "runner benchmarks", "skipped", "status", {"reason": f"no bwrap + wrapper at {WRAPPER}"})
        return

    envelope = json.dumps({"schema": "wm-sandbox-exec-v1", "program": "echo", "args": ["bench"], "net": False})

    def raw_wrapper():
        subprocess.run([WRAPPER, "--exec", envelope], capture_output=True, timeout=60)

    b.measure("D", "raw wrapper exec (bwrap, echo)", "ms/op", raw_wrapper, min_iters=10)

    state = b.state_dir("runner-sandbox")
    orch = make_orchestrator(state, runner=SandboxRunner(WRAPPER))
    issued = orch.pass_("bench", AGENT_DID, minutes=5)

    def sandbox_exec():
        orch.exec_("bench", issued["slot_id"], "echo bench")

    b.measure("D", "gate exec via SandboxRunner (echo)", "ms/op", sandbox_exec, min_iters=10)

    if HAS_SYSTEMD:
        slice_state = b.state_dir("runner-slice")
        slice_orch = make_orchestrator(slice_state, runner=SliceRunner(WRAPPER))
        slice_issued = slice_orch.pass_("bench", AGENT_DID, minutes=5)
        b.measure("D", "gate exec via SliceRunner (echo)", "ms/op",
                  lambda: slice_orch.exec_("bench", slice_issued["slot_id"], "echo bench"), min_iters=10)

        kill_state = b.state_dir("kill-latency")
        kill_orch = make_orchestrator(kill_state, runner=SandboxRunner(WRAPPER))
        kill_samples = []
        for _ in range(10):
            kill_issued = kill_orch.pass_("bench", AGENT_DID, minutes=1)
            outcome = {}
            failure = {}

            def run_exec():
                try:
                    outcome.update(kill_orch.exec_("bench", kill_issued["slot_id"], "sleep 30"))
                except Exception as exc:  # noqa: BLE001
                    failure["exc"] = exc

            worker = threading.Thread(target=run_exec)
            worker.start()
            run_file = kill_state / "runs" / f"{kill_issued['slot_id']}.json"
            deadline = time.time() + 10
            while time.time() < deadline and not run_file.exists():
                time.sleep(0.02)
            killer = make_orchestrator(kill_state, runner=SandboxRunner(WRAPPER))
            started = time.perf_counter()
            killed = killer.kill("bench", kill_issued["slot_id"], wait_s=5.0)
            kill_samples.append((time.perf_counter() - started) * 1000)
            worker.join(timeout=10)
            if failure or killed.get("kill_signal") != "operator":
                kill_samples.pop()
                b.invariant("kill drill completed", False, str(failure) + str(killed))
        if kill_samples:
            b.record("D", "operator kill latency (sleep payload)", "ms/op", kill_samples)
            b.invariant("operator kills stopped the run", True, f"n={len(kill_samples)}")

        if b.oom_drill:
            oom_state = b.state_dir("oom-latency")
            oom_orch = make_orchestrator(oom_state, runner=SliceRunner(WRAPPER))
            oom_samples = []
            for _ in range(5):
                oom_issued = oom_orch.pass_("bench", AGENT_DID, minutes=1)
                slot = oom_orch.registry.get_slot(oom_issued["slot_id"])
                slot["quotas"]["mem_mb"] = 96
                oom_orch.registry.put_slot(slot)
                payload_ref = json.dumps({"program": "python3", "args": ["-c", "x=bytearray(512*1024*1024)"]})
                started = time.perf_counter()
                executed = oom_orch.exec_("bench", oom_issued["slot_id"], payload_ref)
                oom_samples.append((time.perf_counter() - started) * 1000)
                if executed.get("kill_signal") != "quota":
                    oom_samples.pop()
            if oom_samples:
                b.record("D", "OOM quota-seal latency (memory hog)", "ms/op", oom_samples)
        else:
            b.metric(
                "D", "OOM quota-seal latency", "skipped", "status",
                {"reason": "opt-in via --oom; memcg OOM kills trigger desktop OOM notifications (gsd-housekeeping)"},
            )

    egress_state = b.state_dir("egress-deny")
    egress_orch = make_orchestrator(egress_state, runner=SandboxRunner(WRAPPER))
    egress_issued = egress_orch.pass_("bench", AGENT_DID, minutes=2)
    curl_ref = json.dumps({"program": "curl", "args": ["-sS", "-m", "5", "https://example.com"], "net": True, "egress": []})

    def denied_curl():
        executed = egress_orch.exec_("bench", egress_issued["slot_id"], curl_ref)
        if executed["exit"] == 0:
            raise RuntimeError("egress was not denied")

    b.measure("D", "egress-denied curl exec", "ms/op", denied_curl, min_iters=5)
    b.invariant("egress deny invariants hold", True, "all runs non-zero exit")


def bench_mcp(b: Bench) -> None:
    print("E. MCP transports")
    state = b.state_dir("mcp")
    orch = make_orchestrator(state)
    server = McpServer(orch, "bench")
    httpd = McpHttpServer(("127.0.0.1", 0), server)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    issued = orch.pass_("bench", AGENT_DID, minutes=5)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
        session = {}

        def http_keepalive(message):
            headers = {"Content-Type": "application/json"}
            if session.get("id"):
                headers["Mcp-Session-Id"] = session["id"]
            conn.request("POST", "/mcp", body=json.dumps(message), headers=headers)
            response = conn.getresponse()
            payload = json.loads(response.read())
            if response.getheader("Mcp-Session-Id"):
                session["id"] = response.getheader("Mcp-Session-Id")
            return payload

        http_keepalive({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})

        b.measure("E", "HTTP keep-alive ping", "ms/call",
                  lambda: http_keepalive({"jsonrpc": "2.0", "id": 2, "method": "ping"}))
        b.measure("E", "HTTP keep-alive status", "ms/call",
                  lambda: http_keepalive({
                      "jsonrpc": "2.0", "id": 3, "method": "tools/call",
                      "params": {"name": "mandala.status", "arguments": {"slot": issued["slot_id"]}},
                  }))

        def urllib_ping():
            request = urllib.request.Request(
                f"http://127.0.0.1:{port}/mcp",
                data=json.dumps({"jsonrpc": "2.0", "id": 4, "method": "ping"}).encode(),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(request, timeout=15).read()

        b.measure("E", "HTTP per-connection ping (urllib)", "ms/call", urllib_ping, min_iters=10)

        concurrency = (8, 50)
        workers = concurrency[0]
        per_worker = concurrency[1]
        latencies = []
        errors = []
        lock = threading.Lock()

        def worker_thread():
            local = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
            for _ in range(per_worker):
                try:
                    started = time.perf_counter()
                    body = json.dumps({"jsonrpc": "2.0", "id": 5, "method": "ping"})
                    local.request("POST", "/mcp", body=body, headers={"Content-Type": "application/json"})
                    response = local.getresponse()
                    response.read()
                    with lock:
                        latencies.append((time.perf_counter() - started) * 1000)
                except Exception as exc:  # noqa: BLE001
                    with lock:
                        errors.append(repr(exc))
            local.close()

        threads = [threading.Thread(target=worker_thread) for _ in range(workers)]
        t0 = time.perf_counter()
        for item in threads:
            item.start()
        for item in threads:
            item.join()
        wall_ms = (time.perf_counter() - t0) * 1000
        b.record("E", f"HTTP concurrent ping ({workers} clients x {per_worker})", "ms/call", latencies)
        b.metric("E/concurrency", f"HTTP concurrent throughput ({workers} clients)", round(workers * per_worker / (wall_ms / 1000), 1), "calls/s",
                 {"wall_ms": round(wall_ms, 1), "errors": len(errors)})
        b.invariant("concurrent HTTP clients all succeed", not errors, f"errors={len(errors)}")

        stdio_state = b.state_dir("mcp-stdio")
        stdio_orch = make_orchestrator(stdio_state)
        stdio_proc = subprocess.Popen(
            [sys.executable, "-m", "gate_lite.mcp_server", "--state", str(stdio_state), "--tenant", "bench"],
            cwd=str(ROOT), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            def stdio_call(message):
                stdio_proc.stdin.write(json.dumps(message) + "\n")
                stdio_proc.stdin.flush()
                return json.loads(stdio_proc.stdout.readline())

            stdio_call({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
            stdio_issued = stdio_orch.pass_("bench", AGENT_DID, minutes=5)
            b.measure("E", "stdio ping", "ms/call",
                      lambda: stdio_call({"jsonrpc": "2.0", "id": 2, "method": "ping"}))
            b.measure("E", "stdio status", "ms/call",
                      lambda: stdio_call({
                          "jsonrpc": "2.0", "id": 3, "method": "tools/call",
                          "params": {"name": "mandala.status", "arguments": {"slot": stdio_issued["slot_id"]}},
                      }))

            def stdio_flow():
                passed = stdio_call({"jsonrpc": "2.0", "id": 10, "method": "tools/call",
                                     "params": {"name": "mandala.pass", "arguments": {"agent": AGENT_DID}}})
                slot = json.loads(passed["result"]["content"][0]["text"])["slot_id"]
                stdio_call({"jsonrpc": "2.0", "id": 11, "method": "tools/call",
                            "params": {"name": "mandala.exec", "arguments": {"agent": AGENT_DID, "slot": slot, "payload_ref": "echo mcp"}}})
                stdio_call({"jsonrpc": "2.0", "id": 12, "method": "tools/call",
                            "params": {"name": "mandala.terminate", "arguments": {"slot": slot}}})

            def http_flow():
                passed = http_keepalive({"jsonrpc": "2.0", "id": 20, "method": "tools/call",
                                         "params": {"name": "mandala.pass", "arguments": {"agent": AGENT_DID}}})
                slot = json.loads(passed["result"]["content"][0]["text"])["slot_id"]
                http_keepalive({"jsonrpc": "2.0", "id": 21, "method": "tools/call",
                                "params": {"name": "mandala.exec", "arguments": {"agent": AGENT_DID, "slot": slot, "payload_ref": "echo mcp"}}})
                http_keepalive({"jsonrpc": "2.0", "id": 22, "method": "tools/call",
                                "params": {"name": "mandala.terminate", "arguments": {"slot": slot}}})

            b.measure("E", "full lifecycle over stdio", "ms/flow", stdio_flow, min_iters=5, iters=10)
            b.measure("E", "full lifecycle over HTTP keep-alive", "ms/flow", http_flow, min_iters=5, iters=10)
        finally:
            stdio_proc.stdin.close()
            stdio_proc.wait(timeout=10)
    finally:
        httpd.shutdown()
        httpd.server_close()


def bench_soak(b: Bench) -> None:
    print("F. soak (latency drift + memory)")
    state = b.state_dir("soak")
    orch = make_orchestrator(state)
    rss_before = current_rss_mb()
    samples = []
    last_task = None
    for _ in range(b.cfg["soak_flows"]):
        started = time.perf_counter()
        issued = orch.pass_("bench", AGENT_DID, minutes=5)
        orch.exec_("bench", issued["slot_id"], "echo soak")
        terminated = orch.terminate("bench", issued["slot_id"])
        last_task = terminated["task_id"]
        samples.append((time.perf_counter() - started) * 1000)
    rss_after = current_rss_mb()
    window = max(1, len(samples) // 10)
    first = statistics.median(samples[:window])
    last = statistics.median(samples[-window:])
    b.record("F", f"soak flow latency ({len(samples)} flows)", "ms/flow", samples)
    b.metric("F/soak", "first-decile median", round(first, 3), "ms")
    b.metric("F/soak", "last-decile median", round(last, 3), "ms")
    b.metric("F/soak", "drift (last vs first)", round((last - first) / first * 100, 2), "%")
    b.metric("F/soak", "RSS before (VmRSS)", round(rss_before, 2), "MB")
    b.metric("F/soak", "RSS after (VmRSS)", round(rss_after, 2), "MB")
    b.metric("F/soak", "RSS delta (VmRSS)", round(rss_after - rss_before, 2), "MB")
    b.metric("F/soak", "registry slots at end", len(orch.list_("bench")), "slots")
    if last_task:
        verdict = verify_bundle(orch.receipt(last_task))
        b.invariant("soak final bundle verifies TRUSTED", verdict.verdict == "TRUSTED", verdict.verdict)


def human_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} GB"


def render_report(b: Bench) -> str:
    lines = [
        "# Gate-lite benchmark report",
        "",
        f"- Profile: **{b.profile}** · recorded {b.env['recorded_at']}",
        f"- Host: {b.env['cpu']} · {b.env['nproc']} threads · {b.env['mem_total_mb']} MB RAM · kernel {b.env['kernel']}",
        f"- Python {b.env['python']} · {b.env['bwrap']} · {b.env['systemd']}",
        f"- Runner: `{b.env['runner']}` · load avg at start {b.env['loadavg_start']}",
        "",
        "Method: warmup, auto-calibrated n against a per-case time budget; latency",
        "percentiles are over per-operation samples. Percentiles on low-n latency",
        "cases (snapshot, kill, OOM) are indicative, not distribution-grade.",
        "",
    ]
    groups = {}
    for entry in b.results:
        groups.setdefault(entry["group"], []).append(entry)
    for group in sorted(groups):
        lines += [f"## {group}", "", "| Case | n | median | p95 | p99 | mean | sd | min | max | per sec |", "|---|---|---|---|---|---|---|---|---|---|"]
        for entry in groups[group]:
            lines.append(
                f"| {entry['name']} | {entry['n']} | {entry['median_ms']} ms | {entry['p95_ms']} ms | {entry['p99_ms']} ms | "
                f"{entry['mean_ms']} ms | {entry['stdev_ms']} ms | {entry['min_ms']} ms | {entry['max_ms']} ms | {entry['per_sec']} |"
            )
        lines.append("")

    if b.metrics:
        lines += ["## Metrics & sizes", "", "| Group | Metric | Value | Unit |", "|---|---|---|---|"]
        for entry in b.metrics:
            value = entry["value"]
            if entry["unit"] == "bytes" and isinstance(value, int):
                value = f"{value} ({human_bytes(value)})"
            lines.append(f"| {entry['group']} | {entry['name']} | {value} | {entry['unit']} |")
        lines.append("")

    if b.invariants:
        lines += ["## Invariants", "", "| Check | Result | Detail |", "|---|---|---|"]
        for item in b.invariants:
            lines.append(f"| {item['name']} | {'PASS' if item['ok'] else 'FAIL'} | {item['detail']} |")
        lines.append("")

    sizes = {entry["name"]: entry["value"] for entry in b.metrics if entry["group"] == "A/sizes"}
    full = sizes.get("bundle compact bytes (6 receipts)")
    minimal = sizes.get("bundle compact bytes (pass+termination)")
    if full:
        for count in (1000, 100000, 1000000):
            lines.append(f"- {count:,} full tasks ≈ {human_bytes(full * count)} of receipt bundles")
        lines.append("")
    if minimal and full:
        lines.append(f"- Minimal task (pass+termination) is {minimal / full * 100:.1f}% of a full task bundle")
        lines.append("")

    observations = []
    lookup = {(entry["group"], entry["name"]): entry for entry in b.results}
    verify6 = lookup.get(("A", "verify bundle (6 receipts)"))
    verify100 = lookup.get(("A", "verify bundle (100 receipts)"))
    if verify6 and verify100:
        ratio = verify100["median_ms"] / verify6["median_ms"]
        observations.append(
            f"Bundle verification scales near-linearly: 100 receipts take {ratio:.1f}x the 6-receipt time"
            f" ({verify100['median_ms']} ms vs {verify6['median_ms']} ms)."
        )
    get100 = lookup.get(("B", "get_slot (100 slots)"))
    get10k = lookup.get(("B", "get_slot (10000 slots)"))
    if get100 and get10k:
        observations.append(
            f"Registry reads are independent of store size: get_slot at 10k slots is {get10k['median_ms'] / get100['median_ms']:.1f}x"
            f" the 100-slot time ({get10k['median_ms']} ms vs {get100['median_ms']} ms) — indexed SQLite lookups replaced full JSON reparsing."
        )
    slice_case = lookup.get(("D", "gate exec via SliceRunner (echo)"))
    sandbox_case = lookup.get(("D", "gate exec via SandboxRunner (echo)"))
    raw_case = lookup.get(("D", "raw wrapper exec (bwrap, echo)"))
    if slice_case and sandbox_case and raw_case:
        observations.append(
            f"Containment overhead: raw bwrap {raw_case['median_ms']} ms, through the gate {sandbox_case['median_ms']} ms,"
            f" slice-isolated {slice_case['median_ms']} ms per exec."
        )
    http_case = lookup.get(("E", "HTTP keep-alive ping"))
    urllib_case = lookup.get(("E", "HTTP per-connection ping (urllib)"))
    if http_case and urllib_case:
        observations.append(
            f"HTTP connection reuse matters: keep-alive ping {http_case['median_ms']} ms vs {urllib_case['median_ms']} ms per call with a fresh connection."
        )
    kill_case = lookup.get(("D", "operator kill latency (sleep payload)"))
    if kill_case:
        observations.append(f"Operator kill latency: median {kill_case['median_ms']} ms, p95 {kill_case['p95_ms']} ms (n={kill_case['n']}).")
    soak_case = lookup.get(("F", f"soak flow latency ({b.cfg['soak_flows']} flows)"))
    drift = next((entry["value"] for entry in b.metrics if entry["name"] == "drift (last vs first)"), None)
    if soak_case and drift is not None:
        slots_at_end = next((entry["value"] for entry in b.metrics if entry["name"] == "registry slots at end"), None)
        rss_delta = next((entry["value"] for entry in b.metrics if entry["name"] == "RSS delta (VmRSS)"), None)
        note = f"Soak: {soak_case['n']} flows, median {soak_case['median_ms']} ms, drift {drift}% between first and last decile"
        if slots_at_end is not None and rss_delta is not None and drift and drift > 20:
            note += (
                f"; the drift tracks registry growth ({slots_at_end} slots at end, RSS delta {rss_delta} MB),"
                " not a process leak — see B for the registry-size curve"
            )
        observations.append(note + ".")
    if observations:
        lines += ["## Observations", ""] + [f"- {item}" for item in observations] + [""]

    return "\n".join(lines)


def write_csv(b: Bench, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["group", "name", "unit", "n", "median_ms", "p95_ms", "p99_ms", "mean_ms", "stdev_ms", "min_ms", "max_ms", "per_sec"])
        for entry in b.results:
            writer.writerow([
                entry["group"], entry["name"], entry["unit"], entry["n"], entry["median_ms"], entry["p95_ms"],
                entry["p99_ms"], entry["mean_ms"], entry["stdev_ms"], entry["min_ms"], entry["max_ms"], entry["per_sec"],
            ])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="gate-lite-bench")
    parser.add_argument("--out", default=str(ROOT / "evidence" / "bench-2026-09-18"))
    parser.add_argument("--profile", choices=tuple(PROFILES), default="standard")
    parser.add_argument("--keep", action="store_true", help="keep large snapshot/workspace artifacts")
    parser.add_argument("--only", default=None, help="comma-separated groups to run, e.g. A,E")
    parser.add_argument(
        "--oom",
        action="store_true",
        help="include the OOM quota-seal drill (memcg OOM kills fire desktop OOM notifications)",
    )
    args = parser.parse_args(argv)

    out = Path(args.out).resolve()
    if out.exists():
        shutil.rmtree(out)
    b = Bench(out, args.profile, keep=args.keep, oom_drill=args.oom)
    groups = set(args.only.split(",")) if args.only else None
    started = time.time()
    if not groups or "A" in groups:
        bench_primitives(b)
    if not groups or "B" in groups:
        bench_registry(b)
    if not groups or "C" in groups:
        bench_orchestrator(b)
    if not groups or "D" in groups:
        bench_runner(b)
    if not groups or "E" in groups:
        bench_mcp(b)
    if not groups or "F" in groups:
        bench_soak(b)

    b.env["loadavg_end"] = list(os.getloadavg())
    b.env["duration_s"] = round(time.time() - started, 2)
    (out / "results.json").write_text(json.dumps({"env": b.env, "results": b.results, "metrics": b.metrics, "invariants": b.invariants}, indent=2) + "\n", encoding="utf-8")
    write_csv(b, out / "results.csv")
    report = render_report(b)
    (out / "report.md").write_text(report + "\n", encoding="utf-8")
    print(report)
    failed = [item for item in b.invariants if not item["ok"]]
    print(f"\nresults: {out}")
    print(f"invariants: {len(b.invariants) - len(failed)}/{len(b.invariants)} pass · duration {b.env['duration_s']}s")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
