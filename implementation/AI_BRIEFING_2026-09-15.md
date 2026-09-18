# Technical briefing — MandalaOS / WhiteMagic (2026-09-15)

**Audience:** another AI (or engineer) with no prior context, asked to review,
critique, or continue this work.
**Canonical status doc:** `CURRENT_REALITY_2026-09-13.md` (wins over plans).
**This file:** a self-contained snapshot of the current aim, architecture,
governance model, evidence discipline, and open gaps.

---

## 1. Purpose and thesis

**What we are building.** MandalaOS is a *governed workplace for AI agents* —
an operating-system-shaped deployment whose point is not raw capability but
**accountability**: every agent action observable, attributable, explainable,
and (eventually) limitable. WhiteMagic (WM) is the memory/governance engine
inside it; the OS is the host, boundary, and evidence surface.

**Thesis.** The bottleneck for AI doing real work is not intelligence but
*trust*: if an agent's actions are invisible and unrecorded, no responsible
person, company, or regulator can authorise meaningful autonomy. So we build
the "receipts layer" first, locally, with claim discipline.

**Explicitly NOT claimed:** no new kernel, no microkernel, no Qubes-level
isolation, no kernel-exploit resistance. Containment is shared-kernel
(namespaces, Landlock LSM, sandbox wrappers) and is described honestly in
`MANDALAOS_SOVEREIGN/docs/THREAT_MODEL.md`. The project is pre-publication and
gated (see §8).

---

## 2. Repositories and components

| Repo | Language | Role |
|---|---|---|
| `WHITEMAGIC/WMv9` | Rust workspace | Governance/memory kernel: dharma gate, karma ledger, effect system, sandbox registry, event bus, telemetry galaxy, MCP server + `wm` CLI. Currently **v9.1.6**; `main` carries unreleased Yama changes (9.1.7). |
| `MANDALA_OS/MANDALAOS_SOVEREIGN` | NixOS flake | The OS: declarative NixOS 26.05, hardened kernel, systemd units, WM daemon + read-only MCP, containment matrix, Tetragon capture kit, scripts. Guest kernel 6.18.50, host 7.0. |
| `MANDALA_OS/LAKSHMI` | Python (stdlib only) | Telemetry digestor + policy engine + dashboards: 7-dim Harmony Vector, step-0 policies with hysteresis, Y1.0 actuator router (notify-only), bridge report, living-Mandala UI. |
| `MANDALA_OS` | docs (local-only git) | Canonical status, designs, contracts, publication playbook, session notes. Not published. |

**Contexts:** the sovereign VM is the dogfooding artifact
(`nixosConfigurations.mandala-vm`; `mandala-sovereign` is the installable
config). Nothing runs on bare metal yet.

---

## 3. Architecture (current, observed data flow)

```
guest OS (NixOS VM)
  Tetragon v1.7.1 eBPF  ── kprobe security_file_open (observe only)
        │  tetra getevents -o json (needs a pty: ssh -tt + stty -onlcr)
        ▼
host: yama-collector.py --follow
     maps events → telemetry.observation records
       fields: kind, ts, policy_id, metric, state="observed",
               action="observe", value=<count>, subject="proc:<comm>:<bin>",
               subjects[], evidence[], tags
     fail-soft spool (bounded) on WM outage; sent-log ring for read-back
        │  MCP: telemetry.record (typed) → falls back to memory.create pre-9.1.5
        ▼
WM gateway (127.0.0.1:18790)  ── telemetry galaxy (LMDB + FTS)
        ▲
LAKSHMI sampler (60 s windows, systemd user unit)
  ├─ 7-dim Harmony Vector from /proc, PSI, RAPL/battery, WM karma seam
  ├─ fetch_bridge_inputs:
  │    bus.recent (sandbox_observation events: tool, kind, counts)
  │    memory.search (tetragon records) ⊕ sent-log ring (mirror-first,
  │    deduped by (ts, policy_id, metric); values summed)
  ├─ step-0 policy engine (hysteresis; 7 policies)
  │    transitions → decision records (schema v2, see §4)
  ├─ Y1.0 actuator router: confirmed-only, notify-only, armed via WM_ACTUATION
  └─ mirror: latest.json / history.jsonl / observations.jsonl (bounded rings)
        │
        ├─ dashboard (:3109): /api/live, /api/history, /api/observations, /api/bridge, /mandala
        └─ telemetry galaxy records (durable)
```

**Sandbox runner (separate limb):** WM tools that declare
`Sandbox::Subprocess` route spawns through a runner: `bwrap` wrapper or pure
`landrun` (Landlock) runner. Drift (a declared spawn with no runner, or a
spawn-declared tool bypassing the policy) is counted and emitted as
`sandbox_observation` bus events (exactly-once). The runner is the future
enforcement seam; today it only reports.

---

## 4. Governance model (the substance)

### 4.1 The actuation ladder

| Step | Name | Meaning | State |
|---|---|---|---|
| 0 | observe | record only | live |
| 1 | notify | record + bus event + dashboard | live (Y1.0; bus event needs WM ≥ 9.1.7) |
| 2 | nudge | non-blocking advisory to the subject | not built; gated on FP baseline |
| 3 | throttle | bounded restriction (budget class; never a kill) | not built; gated |
| 4 | isolate | proposal only, human confirms | never automated |

**Rule: no closed loop without hysteresis** — enter ≠ exit thresholds,
`min_dwell_windows`, one-time `confirmed` transition, `cooldown_windows`,
global breaker, per-action decision records, expiry, and `WM_ACTUATION=0`
(disarm is discoverable, availability-first).

### 4.2 Policies (7, all observe-only)

- Dim policies: `responsiveness.below.v1` (0.30/0.50, dwell 5, cooldown 3),
  `stability.below.v1` (0.80/0.95), `energy.over_budget.v1` (0.90/0.97,
  battery/RAPL only), `dharma.blocked.v1` (above 0.5/0.0, dwell 1).
- Bridge policies: `spawn.undeclared.v1`, `sandbox.degraded.v1` (fed by
  sandbox bus events), `shadow.access.v1` (fed by Tetragon records).

### 4.3 Record schemas

Window record (`telemetry.window`): dims, harmony_score, guna, top processes,
events, bridge counts, karma/dharma counters, and
`actuation: {armed, applied}`.

Decision record (`telemetry.observation`, v2 additive): `policy_id`,
`version`, `metric`, `direction`, `value`, `enter`, `exit`,
`min_dwell_windows`, `cooldown_windows`, `state`
(`observing|confirmed|clear`), `action`, `subject`, `subjects`, `step`,
`actuator`, `undo_token`, `expires_at`, `evidence`.

### 4.4 Subject identity

`tool:<name>` (sandbox events), `proc:<comm>:<basename>` (Tetragon, never
pid-only; pid stays in evidence), `dim:<metric>` (telemetry dims),
`mandala:<id>` reserved. Rules: stable across windows; unresolved subject
stays notify-only; captured subjects always win.

### 4.5 Actuator contract

`design/ACTUATOR_CONTRACT_2026-09-15.md`: router consumes **confirmed**
transitions only; idempotent per `(ts, policy, state)`; one action per dwell;
expiry without renewal; undo tokens for any enforced step; breaker to step 0;
`WM_ACTUATION=0` re-read live. **Y1.0 (router, notify) and Y1.1 (subjects)
implemented.** Y1.2 nudge / Y1.3 throttle are gated on per-policy
zero-false-positive observation windows; Y1.4 ports evaluation+router into
`wm-governance` (Rust) so the VM can evaluate locally.

---

## 5. Design laws (invariants to preserve)

1. **Observe before enforce**; no blocking without a clean observation window.
2. **No silent zeros** — unavailable is disclosed (hatch/stale/empty-state),
   never rendered as a healthy zero.
3. **Fail-soft, availability-first** — spools, rings, mirrors; OS sampling
   never depends on WM being up.
4. **Every action attributable** — policy id + version, subject, thresholds,
   evidence windows, actor (`system:policy` vs `user`).
5. **Rollback first-class** — every actuator has an undo path; throttle
   states self-heal.
6. **Claim discipline in docs** — "verified" vs "target"; stale claims get
   banners or are deleted; `CURRENT_REALITY` wins over plans.
7. **Plain language first, metaphor second** — the Sanskrit names (Yama,
   Lakshmi, dharma, karma) are glossed, never load-bearing.
8. **Receipts culture** — decisions recorded to WM session memory; session
   notes and handoffs for every working pass.

---

## 6. What is proven (evidence, 2026-09-15)

- **S4 / real eBPF capture:** Tetragon v1.7.1 in-guest (bundle install,
  `--bpf-lib`), policy `observe-etc-shadow`; collector streamed 67–72 events
  per run; records landed; `shadow.access.v1` transitioned
  observing→clear; dashboard merged mirror+galaxy.
- **Routine capture tooling:** `scripts/capture_window.sh` (one command; VM
  build GC-rooted at `~/.local/state/mandalaos/vm-image`; standard triggers;
  self-contained report dir `~/.local/share/mandala-captures/<UTC>/`);
  `LAKSHMI/bridge_report.py` (per-policy states/inputs/FP candidates). First
  scripted run: 72 events → 4 records, 0 spooled, 0 FP candidates.
- **Containment:** in-guest matrix 13/13 green (Landlock × bwrap × landrun
  resolution documented in `SANDBOX_LAYERS_2026-09-12.md`).
- **Tests:** LAKSHMI 94 + dashboard 32; collector 8; WM crates green
  (wm-cognitive incl. 713+ tests); fmt + clippy `-D warnings` clean on the
  changed crates.
- **Release engineering:** v9.1.6 tagged/certified; sovereign pinned to
  v9.1.6 (`391e03f`); closure builds `whitemagic-9.1.6` (version derived from
  `Cargo.toml`, not hardcoded); signing-key custody register with four
  verified copies.

---

## 7. Open gaps (ordered by consequence)

1. **Enforcement is unearned** (by design): no nudge/throttle yet; needs a
   per-policy false-positive baseline from routine captures.
2. **Evaluation lives on the host**, not in the VM — Python step-0 + router.
   Y1.4 (Rust port to `wm-governance`) is the durable fix; until then
   "Sovereign Edition" depends on the host fleet for policy.
3. **Coverage is thin:** only shadow-access from the original trio (egress,
   shadow-write, crypto-miner) are unimplemented; child-level runner-denial
   parsing is deferred; sandbox drift signals are counter-based.
4. **Operational packaging:** Tetragon is hand-installed (Nix packaging
   deferred), the collector has no systemd unit, the 18798 dev serve
   rate-limits bursty tool calls (`memory.list`/`memory.read`).
5. **Bridge trust model undisclosed:** observation records are trusted-local;
   no signing/collector identity. `THREAT_MODEL.md` covers containment, not
   the bridge.
6. **Publication gates:** soak (≥72 h accumulated *active* time; redefined
   2026-09-15 with suspend excluded and disclosed), stranger install (≥4/5;
   dry run fixed 5 of 6 gaps; SHA pinning open), repo hygiene (near done).
7. **9.1.7 unreleased** — the notify bus event (`actuation_notify`) and the
   `wm doctor` bridge-feed line ride it; until then notify degrades to the
   decision record.

---

## 8. Current objective and next moves

**Objective now:** turn the proven observation chain into *evidence over
time*, then earn the first enforcement step.

1. **Run captures routinely** (script exists; ~15 min/window) and let the
   72 h soak accumulate; review with `bridge_report.py`.
2. **First promotion review** once a policy shows zero false-positive
   candidates over its observation window → Y1.2 nudge, then Y1.3 throttle
   (budget-class shaping, never a kill).
3. **Ship 9.1.7** so notify bus events are live, then site/release facts sync.
4. **Close the publication gates** (soak evidence bundle, stranger testers
   from `publication/STRANGER_INSTALL_PROTOCOL.md`, hygiene checklist).
5. **Y1.4**: move policy evaluation + router into the VM (Rust), same
   contract, so the sovereign claim is real.

**Non-goals right now:** console/desktop polish (living-Mandala P1+), kernel
work, Qubes/seL4 paths, OPA/Cedar, automatic isolation.

---

## 9. Interfaces for a reviewing AI

**Run tests**

```bash
cd MANDALA_OS/LAKSHMI && python3 -m unittest test_actuator test_lakshmi test_dashboard
cd MANDALA_OS/MANDALAOS_SOVEREIGN/scripts && python3 -m unittest test_yama_collector
cd WHITEMAGIC/WMv9 && cargo test -p wm-cognitive && cargo clippy -p whitemagic -p wm-cognitive --all-targets -- -D warnings
```

**Run an instrumented capture** (host must have Nix, the VM cache, and a
supported kernel for guest Tetragon)

```bash
cd MANDALA_OS/MANDALAOS_SOVEREIGN
scripts/capture_window.sh                 # 15 min; report in ~/.local/share/mandala-captures/
```

**Gate/soak evidence**

```bash
python3 MANDALA_OS/publication/soak_check.py --endpoint http://127.0.0.1:18798 \
    --mirror ~/.local/share/lakshmi-edge/history.jsonl --suspend-journal
python3 MANDALA_OS/LAKSHMI/bridge_report.py --endpoint http://127.0.0.1:18790 --hours 168
```

**Where things live**

- Contracts/designs: `MANDALA_OS/design/` (`ACTUATOR_CONTRACT`, `ACTUATION_HYSTERESIS`, `GNOSIS_PORTAL_UI`).
- Bridge design (S1–S4, D1–D6): `MANDALA_OS/implementation/yama-v0-bridge-design.md`.
- Gates: `MANDALA_OS/publication/` (playbook, stranger protocol, soak checker).
- Runbooks: `MANDALAOS_SOVEREIGN/docs/S4_TETRAGON_RUNBOOK.md`, `GETTING_STARTED.md`, `THREAT_MODEL.md`.
- Status/supersession: `MANDALA_OS/CURRENT_REALITY_2026-09-13.md` (+ §9 original-notes annex).
- Session continuity: `MANDALA_OS/session-notes/` and the WM session store
  (tools `session.start/record/checkpoint`, `memory.*` over MCP).

**Review questions we would value:** (a) does the actuation contract have a
failure mode we have not bounded (especially expiry/undo under evaluator
restarts)? (b) is the subject-identity scheme sufficient for per-subject
throttle? (c) what is the smallest honest evidence bundle for the stranger
gate? (d) any place where claim discipline is weaker than the docs imply?
