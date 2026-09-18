# Gate-lite dogfood evidence — 2026-09-18T02:54:54Z

Host: Linux-7.0.0-31-generic-x86_64-with-glibc2.39 · bwrap bubblewrap 0.9.0
Runner: `/home/lucas/.local/bin/mandala-sandbox` (slice mode: WM_GATELITE_SLICE=1)
Checks: **33/33** in 7.24s

| Drill | Check | Result | Detail |
|---|---|---|---|
| G1 | exec exit 0 | PASS | stdout_hash=sha256:5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03 |
| G1 | exec inside slice quota | PASS | no quota/operator kill |
| G1 | $0 settlement recorded | PASS | dogfood-0001 |
| G1 | bundle TRUSTED (6 receipts) | PASS | TRUSTED |
| G7/snapshot | frozen + artifact | PASS | snap-50c9a811d4bd 67B |
| G7/snapshot | exec refused while frozen | PASS | {"error": "slot is frozen"} |
| G7/snapshot | bundle TRUSTED | PASS | [] |
| G7/restore | runner wrote workspace artifact | PASS | sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |
| G7/restore | workspace restored byte-identical | PASS | sha256:eb5198cceb7957dd98fd5e3c76f842683704493ccfced681c602f48b81e2d888 |
| G7/restore | artifact content present | PASS | /home/lucas/Desktop/MANDALA_OS/gate-lite/evidence/2026-09-18/state/workspaces/slot-44d4cde6bf26/artifact.txt |
| G7/restore | exec in restored slot | PASS | sha256:09204dbfbdb8fc121fb2a47988fe1a42a1981ac4e16ea4afc915e2d87b40d324 |
| G7/restore | bundle TRUSTED | PASS | [] |
| G7/expiry | exec refused after expiry | PASS | {"error": "slot is expired"} |
| G7/expiry | slot sealed as expired | PASS | expired |
| G7/expiry | termination time_expired | PASS | {"reason": "time_expired", "limits_at_stop": {"cpu_ms": 300000, "wall_ms": 0, "spend_minor": 0, "currency": "USD"}, "remaining": {"cpu_ms": 0, "wall_ms": 0, "spend_minor": 0, "currency": "USD"}} |
| G7/expiry | bundle TRUSTED | PASS | [] |
| G3 | undeclared egress denied (non-zero exit) | PASS | exit=6 |
| G3 | denial recorded in task.execution.egress | PASS | {"destination": "undeclared", "bytes": 0, "allowed": false, "enforcer": "bwrap --unshare-net", "denied_reason": "net requested without declared destinations"} |
| G3 | bundle TRUSTED | PASS | [] |
| G6 | run journaled | PASS | /home/lucas/Desktop/MANDALA_OS/gate-lite/evidence/2026-09-18/state/runs/slot-f84deb1429d6.json |
| G6 | kill within 5s | PASS | 238ms |
| G6 | kill_signal=operator | PASS | {"slot_id": "slot-f84deb1429d6", "state": "terminated", "kill_signal": "operator", "receipt_id": "urn:uuid:01a0b270-3116-7cf2-be6d-176c44fd1b97", "exec_active": true} |
| G6 | run stopped and journal cleared | PASS | exit=0 signal=operator |
| G6 | termination receipt operator | PASS | {"kill_signal": "operator", "operator_kill_latency_ms": 43} |
| G6 | bundle TRUSTED | PASS | [] |
| G2 | memory overrun killed slot | PASS | exit=137 reason=quota |
| G2 | termination quota/memory_max | PASS | {"reason": "quota", "limits_at_stop": {"cpu_ms": 300000, "wall_ms": 60000, "spend_minor": 0, "currency": "USD"}, "remaining": {"cpu_ms": 0, "wall_ms": 59000, "spend_minor": 0, "currency": "USD"}, "kill_signal": "quota", "killed_by": "memory_max", "observed": {"exit": 137, "stdout_hash": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"}} |
| G2 | bundle TRUSTED | PASS | [] |
| P1/disclosure | redact re-signs the tail | PASS |  |
| P1/disclosure | salt withheld -> PROVISIONAL | PASS | PROVISIONAL |
| P1/disclosure | disclosed -> TRUSTED | PASS | TRUSTED |
| G8 | exec refused (rc=3, emitter_unavailable) | PASS | {"error": "receipt emitter unavailable: [Errno 13] Permission denied: '/home/lucas/Desktop/MANDALA_OS/gate-lite/evidence/2026-09-18/state/receipts/urn:uuid:01a0b270-385d-7fb0-b765-cb7c63b83543.tmp'", "code": "emitter_unavailable"} |
| G8 | emitter restored, exec proceeds | PASS | sha256:e209f13d112294680541219a291f2607710e7a2f61768cca9496b23a17e2201e |

Receipt bundles: `receipts/` · machine log: `run.json` · CLI transcript: `transcript.txt`

Verify any bundle offline:
`python3 -m continuity_receipt.verify receipts/<file>.json`
