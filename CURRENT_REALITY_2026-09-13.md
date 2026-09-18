# MandalaOS — Current Reality (2026-09-13)

**Status:** canonical status + supersession map, written after a synthesis pass
over the 2026-04→09 plan corpus. When a plan contradicts this doc, this doc
wins — and the plan should carry a banner pointing here.

---

## 1. What is actually built (verified)

| Layer | State | Evidence |
|---|---|---|
| Governance core (WMv9) | Landlock v0/v1, **B2 subprocess runner** (envelope `wm-sandbox-exec-v1`), B3 dharma counters, typed karma debt, engagement tokens on mesh locks, **telemetry galaxy** + `os_telemetry_threshold` | whitemagic `fix/ci-green` @ `c2d837c` (pushed); suites 170/172/511/714/824/267 green; SANDBOX_LAYERS, SESSION_HANDOFF §9-11 |
| Sovereign OS | NixOS 26.05 flake; VM boots in QEMU; daemon + read-only MCP (host 28795) + host embedder bridge; hardened units | mandalaos-sovereign @ `3b8d67f` (pushed) |
| Containment | in-guest matrix **13/13 green** (rebuilt VM 2026-09-14, kernel 6.18, incl. the pure-Landlock runner checks); bwrap wrapper with `--exec` envelope; **`landrun-sandbox` pure-Landlock runner for Landlock stores** (daemon keeps `WM_LANDLOCK=1` *and* contained spawns); explicit `WM_SANDBOX_RUNNER` per unit; `/run/current-system` bind | `/etc/mandala/verify-sandbox.sh`; `wm doctor` §11d-2; SANDBOX_LAYERS §3-7/§4 |
| Telemetry | Lakshmi 7-dim digestor; 1-min windows → telemetry galaxy; bounded spool replay; change-based threshold events | lakshmi @ `ac9f7b4` (pushed); 25 tests; fail-soft drill |
| Policy (Yama) | observe-only feasibility **PASS**: Tetragon v1.7.1 in-guest, BTF, TracingPolicy loaded, `/etc/shadow` access captured; 0.03 % CPU / 66 MB | §4, experiment 2026-09-13 |

**Measured VM snapshot (idle, daemon + MCP running):** 390 Mi / 3.8 Gi,
load 0.33, citta cycles ~50 s (score 0.85, 48 °C), `wm doctor` profile
contract OK (full, 294 tools), `subprocess_sandbox` active. The old docs'
perf table (420–580 MB idle) was a *target*; this is the first measured row
and it meets it.

## 2. Resolved decisions

- **Form:** Sovereign Edition is the build-now artifact (real Nix installed,
  VM dogfooded). Qubes stays gated on funding + hardware; Node/Edge later.
- **Isolation claim:** containment of tool/agent behavior — never
  "Qubes-level"; kernel exploits are out of scope (PLATFORM_DIRECTION §2).
- **Yama v0 shape: C** — governance-native v0 (observe-first over existing
  telemetry + the runner as the enforcement seam) with the Tetragon
  feasibility question answered (PASS). Falco/OPA/Cedar defer to later
  passes; the original three sprint policies return on the next pass.
- **Daemon × serve:** read-only split + explicit turn-taking
  (whitemagic `docs/DAEMON_SERVE_COEXISTENCE.md`).
- **Vehicle:** VM-only dogfooding for now (bare-metal gate blocked: 29 G free
  < 60 G; `SD_CARD1` is archive-only and untouchable).

## 3. Supersession map

| Doc | Status | Note |
|---|---|---|
| `PLATFORM_DIRECTION_2026-09-12.md` | **active** (canonical strategy) | its open decisions 1–3 are now closed (see §2) |
| `feasibility/harmony-vector-spec.md` | **active** | thresholds/scoring remain authoritative for Lakshmi + policy |
| `implementation/lakshmi-yama-sprint-plan.md` | **adjusted** | "Reality-adjusted v0" section appended |
| `feasibility/mandalaos-feasibility-roadmap.md` | superseded (phases) | assumed Qubes-first / microkernel phases; banner added |
| `feasibility/prototype-sprint-plan.md` | superseded (stack) | Qubes-first sprint; observability stack staged per §4 |
| `implementation/MANDALAOS_V0_PLAN_2026-09-10.md` | gated / parallel track | Qubes plan unchanged but inactive; not the current build |
| `realization/*` (v0.1 SPEC, shelter, MAPPING, Jan handoff, strategy) | historical | pre-Rust lineage; statuses stale |
| `implementation/QUBES_PATH_ASSESSMENT_2026-09-10.md` | reconciled reference | R&D-track rationale; header already notes reconciliation |
| `implementation/ADOPTION_IMPLICATIONS_2026-09-10.md` | **active gating** | we knowingly build pre-trigger; its release/GTM gates still apply |
| `implementation/wm-rust-effect-port-plan.md` | executed | F-3 landed in WMv9 |
| `implementation/MandalaOS_Phase_CD_Implementation__*.md` | historical | v24 Python lineage claims, not WMv9 reality |
| `implementation/lakshmi-yama-sprint-plan.md` (stack) | partially deferred | Tetragon first; Falco/OPA/Prometheus later |

## 4. Yama v0 (shape C)

**Definition:** policy over the telemetry and containment already shipped.
Observation comes from the telemetry galaxy, `os_telemetry_threshold`
events, the sandbox runner, and (new) Tetragon observe events. Enforcement
uses the existing seams (bwrap/Landlock runner). The observe-first rule is
unchanged: no blocking without a zero-false-positive window.

**Feasibility record (2026-09-13, in-guest):**

- Tetragon v1.7.1 release binary, sha256 verified; BTF discovery OK
  (`/sys/kernel/btf/vmlinux`); base sensor loaded; gRPC up.
- TracingPolicy `observe-etc-shadow` (kprobe `security_file_open`,
  Postfix `/etc/shadow`, no action = observe) loaded successfully.
- Captured `unix_chkpwd` and `cat` opening `/etc/shadow` plus process-exec
  events — 16 events / 12 s.
- Overhead: 3.28 ms CPU / 10 s idle (~0.03 % of a core), 66 MB RSS —
  far inside the sprint budget (≤2 % CPU, ≤200 MB).
- Cleanly stopped; guest restored.

**First observe policies (v0):**

1. `/etc/shadow` access — proven feasible in-guest.
2. Sandbox-denial and undeclared-spawn events from the runner + bus —
   observable today, no new dependencies.
3. Process-egress observation — when the W2 decision layer exists.

**Next pass (explicitly deferred):** the sprint's original three (process
egress block, shadow write block, crypto-miner signature) plus other
additions; Falco for detection breadth; OPA/Cedar for consent decisions;
Nix packaging of Tetragon for production.

**The open engineering gap** is not collection — it is the bridge:
Tetragon/runner/bus events → WM (galaxy or bus) → a policy evaluation
point. That bridge is the substance of Yama v0 implementation.

**Update 2026-09-15 — the bridge is complete through evaluation; the gap moved
to actuation.** S4 executed for real: rebuilt VM, Tetragon v1.7.1
`observe-etc-shadow` (monitor_only), collector streamed 67 events → 3 records
into the live fleet store, and the step-0 engine transitioned
`shadow.access.v1` to `observing` (value 5, feed-summed); evidence in
`session-notes/2026-09-15_s4-tetragon-observe.md`. The Tetragon read path is
mirror-first (bridge design D6: collector sent-log ring, so recency no longer
depends on FTS ranking). The next gap is executor-shaped:
`design/ACTUATOR_CONTRACT_2026-09-15.md` defines subject identity, the
policy→actuator router, the actuator catalog with undo/expiry, and
`WM_ACTUATION=0`; Y1.0 (notify-only router skeleton) is the first buildable
slice and ships no enforcement.

## 5. Open decisions

- **Dashboard (thread 3): RESOLVED 2026-09-13** — static page + stdlib
  reader, no Tauri; history = local mirror + galaxy merge. Shipped in the
  lakshmi repo (`dashboard.py`, `dashboard.html`, sampler mirror, user
  units; `127.0.0.1:3109`). Open tuning: display window 60 s vs the
  spec's 300 s fairness target (currently disclosed in the dim note).
- **Release (4C):** `fix/ci-green` is 37 commits ahead of `origin/main`;
  choose target version (9.1.4 vs 9.2.0) and channels (full public vs
  host-only fast path).
- **Guest WM is one slice behind** (built before the telemetry galaxy):
  rebuild from `c2d837c` when in-guest telemetry or the policy bridge starts.
- **In-guest vectors = 0:** run a `memory.reembed` backfill if hybrid recall
  inside the VM matters for dogfooding.
- **Retention (2026-09-13): tools shipped.** `telemetry.record` /
  `telemetry.rollup` / `telemetry.prune` (whitemagic `a7cbe80`) implement the
  window (7 d) + rollup (90 d) tiers; `prune` is destructive + dry-run-first,
  and the dharma gate can veto it under stress (observed). **Closed
  2026-09-14 early:** read-only `telemetry.retention` planner (v9.1.5+, never
  confirm/dharma-gated) and the weekly `wm-telemetry-retention.timer` (Sun
  05:10, planner-then-confirmed-prune) are wired and live on the gateway
  store; the hourly rollup timer already existed.
- **Actuation ladder:** design fixed in
  `design/ACTUATION_HYSTERESIS_2026-09-13.md` — enter≠exit thresholds, dwell,
  cooldown, global breaker, attributable decision records, rollback;
  implementation deferred (no closed loop yet). **Step 0 (observe) is LIVE
  2026-09-13 with the full contract:** four policies (bands + `min_dwell` +
  one-time `confirmed` + `cooldown` gating) emit `telemetry.observation`
  decision records; dashboard **Policies** panel shows state/value/band/
  cooldown. Records prefer the typed `telemetry.record` observation kind
  (pushed to main `38bf66e`, rides v9.1.5) with a `memory.create` fallback
  on v9.1.4. Remainder of the ladder (notify/nudge/throttle/isolate) stays
  deferred by design.

## 6. Known deltas / nits

- **In-guest Landlock is `partial`** (guest kernel 6.18, ABI v8) while the
  host kernel 7.0 reports `enforced`. Disclosed by design; if VM evidence
  is ever used for enforcement claims, state the delta (or move the guest
  kernel forward).
- The matrix's "egress probe (https://example.com): unreachable" line is
  **expected** in the default profile (network isolated); consider wording
  it as expected rather than info.
- Old perf numbers are targets; §1's snapshot is the measured baseline.
- **Transient systemd units on NixOS are a trap** (learned live): they have
  no `/bin/bash` (only `/bin/sh`), a minimal PATH (`curl`/`sleep`/`date` are
  not found — set `Environment=PATH=/run/current-system/sw/bin`), and
  `PrivateTmp` hides `/tmp` (run scripts from `/home`, not `/tmp`). A silent
  `203/EXEC` failure is the symptom.
- **`/etc` is read-only on NixOS**: runtime systemd drop-ins must go in
  `/run/systemd/system/<unit>.d/`; anything permanent belongs in the Nix
  module (as the embedder env now does).
- **Host fleet has no subprocess runner**: `subprocess_sandbox` on the host
  reports `active: false` (the wrapper is an OS-layer component and the host
  has no `mandala-sandbox`), so declared spawn tools loud-degrade to
  unconfined there. Options: accept (containment is the VM's job) or install
  a portable host wrapper from the sovereign module. Not yet decided.
  *(Resolved 2026-09-13: wrapper installed + wired; see §8 item 5 and the
  Landlock × runner conflict below.)*
- **Landlock v0 × subprocess runner: mutually exclusive for namespaces,
  resolved for Landlock stores (2026-09-14).** Landlock denies filesystem
  topology modification (all mounts) while a domain is active; bwrap requires
  `mount(MS_SLAVE)`. Reproduced on host (kernel 7.0/bwrap 0.9) and VM
  (6.18/0.11) via landrun; a `/proc` grant was prototyped (keeps ruleset
  `enforced`) but cannot fix the mount step — nothing shipped, so v0 was not
  widened for a non-fix. Stores choose one mechanism: fleet chose the runner
  (wmv9's `landlock.conf` disabled, reversible). **Resolution: rulesets
  stack, so a pure-Landlock runner does work under a domain** —
  `scripts/landrun-sandbox` (sovereign; same `--exec` contract) is the B2
  runner for Landlock stores; the VM daemon now keeps `WM_LANDLOCK=1` *and*
  routes its declared spawns through it, while the read-only serve keeps
  bwrap. Evidence in SANDBOX_LAYERS §3-7 and §4.

## 7. Publication gates (Labs page / public sovereign repo)

Source of truth: `ADOPTION_IMPLICATIONS_2026-09-10.md` (gated GTM) +
`PLATFORM_DIRECTION_2026-09-12.md` §2 (claim discipline). Do not publish
ahead of these; each is checkable evidence, not a vibe.

- [x] **Fleet on v9.1.4 (2026-09-13 night)** — artifact sha `d55b158a…`
      verified against the signed manifest, backed up as
      `wm.bak-9.1.3-20260913`, installed to `~/.local/bin/wm`, selftest 8/8
      on the real machine; all 7 scopes report v9.1.4 and the gateway shows
      `all_reachable: true` (one live finding: a stop/start race kept the
      old inode for `wm-serve@wmv9` until a real restart — watch for silent
      inode retention on unit restarts).
- [x] **Guest parity (2026-09-13 night)** — guest `wm 9.1.4` at branch tip
      `16de9ae` (one hardening commit past the tag), matrix green, daemon +
      read-only MCP active, 301 tools incl. the telemetry surface, B2 runner
      active. Embedder env added to the read-only service
      (`mandalaos-sovereign cb3cb91`; runtime drop-in verified hybrid).
- [ ] **Edge galaxy: ≥72 h of accumulated active soak time** *(gate redefined
      2026-09-15, public: host suspend is excluded and disclosed; every other
      interruption resets the run — definition in
      `publication/GATE_EVIDENCE_PLAYBOOK.md`)* — **not met as of 2026-09-15**:
      the soak run (18798) holds **13.9 h of 72 h active** since
      2026-09-14T18:27Z (8.25 h suspend excluded, resume 23 s); the fleet run
      (18790) is ≈9.7 h. Projection: ≈2026-09-18 if the host stays awake,
      ≈2026-09-19/20 with normal night sleeps. Verification:
      `publication/soak_check.py --suspend-journal`; bundles in
      `publication/evidence_<date>/`.
- [x] **In-guest recall (2026-09-13 night)** — reembed backfill: 11 batches,
      244 embedded, 0 errors; store at 242 vectors + 20 cache; hybrid recap
      verified through the read-only MCP (`recall_mode: hybrid`).
- [x] **Honest gaps + threat model one-pager** — drafted 2026-09-14 at
      `mandalaos-sovereign/docs/THREAT_MODEL.md`: containment ≠ hypervisor
      isolation; no kernel-exploit claims; known deltas from §6 included;
      claim discipline + verification commands. Publish with the repo/page.
- [ ] **Stranger install** — ADOPTION Gate-2: ≥4/5 unassisted installs with
      no data loss, silent corruption, or undisclosed network transfer.
- [ ] **Repo hygiene** — whitemagic release tagged and sovereign pinned to
      that tag; sovereign README "what works today / what's next" derived
      from this doc.

Evidence bundle per gate: dashboard screenshots, matrix output, `/status`
JSON, Tetragon observe log, and a CURRENT_REALITY snapshot at that date.

## 8. Shared follow-up queue (v9.1.4 → next)

**Release-engineering lane (parallel session):**

1. **Release-health record + registry reconciliation — DONE 2026-09-14
   early.** `scripts/release_health.py` probes GitHub Release assets, all 15
   workspace crates (crates.io), npm, Docker Hub, and the official MCP
   registry for one version; writes `release-health.json` (exit 0/1).
   `.github/workflows/release-health.yml` runs it on Release completion +
   daily 04:10 UTC, retries laggards idempotently, re-probes, certifies
   `npm install` + `docker run` by running `wm selftest`, uploads the record
   to the GitHub Release as the single source of truth, and goes red only if
   a surface is still behind. Verified locally against 9.1.4 (healthy) and
   9.9.9 (lagging, exit 1).
2. **`wm selftest` in the release smoke gate — DONE 2026-09-14 early.**
   `release.yml` build matrix now runs `wm selftest --json` on all five
   targets (Linux gnu/musl, macOS x86/arm, Windows) before packaging; the
   health workflow additionally certifies the npm and Docker install paths
   end-to-end. The curated smoke test stays as the deeper Linux check.
3. **First live `wm update` install at 9.1.5** — the transactional path is
   dry-run proven; the first real self-update is the true test. **Prep done
   2026-09-14 (parked):** `scripts/version_truth.py` (15 surfaces,
   check/set, historical exemptions) wired into `release.sh` preflight bump,
   crates order derived from cargo metadata, CHANGELOG draft `[9.1.5]`
   written, and a full `release.sh 9.1.5 --dry-run` is green. No bump/tag/
   deploy — more trunk changes are expected before the ceremony.
4. **`wm setup` write support for JSONC/TOML — DONE 2026-09-14 early.**
   OpenCode `opencode.jsonc` is patched by a string/comment-aware structural
   editor (comments and formatting preserved; comment-free configs take the
   pretty-JSON path); Codex `config.toml` is edited via `toml_edit` (comments
   preserved). Every write is backup-first, read back, and re-parsed, and the
   edited JSONC must round-trip to the intended value before writing.
   Onboarding text now states the contract (“explicit routes are the
   contract”) in `wm setup` output and MCP_CONFIG_GUIDE. WMv9 `main`
   `721b114`; 11 setup tests + 279 wm-mcp lib tests green; clippy clean; CLI
   E2E on a temp HOME.

**MandalaOS lane (this track):**

5. **Portable host containment wrapper — DONE 2026-09-13.**
   `mandalaos-sovereign/scripts/mandala-sandbox` (bwrap+jq, same
   `--exec`/`--net` contract) installed at `~/.local/bin/mandala-sandbox`,
   wired via instance env files + gateway/mesh drop-ins
   (   `WM_SANDBOX_RUNNER`); live spawn verified (`oss.bounty.status` →
   `gh_available: true` with runner disclosure). **Constraint characterized
   and closed** (see §6): Landlock denies all mounts while a domain is
   active, so bwrap can never run under it — reproduced host + VM, with
   upstream documentation. A prototyped `/proc` grant was **not shipped**
   (it cannot fix the mount step and would widen confinement). No release
   action; the either/or policy stands. **Optional future delivered
   2026-09-14:** pure-Landlock `landrun-sandbox` runner (sovereign) for
   Landlock stores, wired into the VM daemon; see §6 and SANDBOX_LAYERS
   §3-7/§4.
6. **Fleet telemetry hygiene — DONE 2026-09-14 early.** Read-only
   `telemetry.retention` planner (WMv9 `main`, rides v9.1.5: windows 7 d /
   rollups 90 d horizons, observation inventory marked unmanaged, no confirm
   or dharma gate) + weekly `wm-telemetry-retention.timer` (Sun 05:10,
   `Persistent=true`, planner-first then confirmed prune) installed on the
   gateway store; graceful on pre-9.1.5 fleets (planner reports Unknown tool,
   prune alone runs — live-verified: 77 scanned, 0 candidates). The hourly
   rollup timer already exists. Scratch-store E2E verified the planner shape;
   a wet prune under load was dharma-vetoed exactly as the planner predicts.
7. **Honest-gaps + threat-model one-pager** — publication gate; draft from
   §6 + PLATFORM_DIRECTION §2.
8. **Signing-key off-machine backup — DONE 2026-09-13.** An encrypted
   off-machine backup was created and round-trip verified; the passphrase is
   stored separately. Custody specifics (media, hashes, locations) are tracked
   in the private security register and deliberately omitted from this
   snapshot.

**Other session's queue (keep MandalaOS feature gated):** website facts
9.1.2 → 9.1.4, server card 9 → 11 tools, adoption numbers,
server.mcpb/Smithery, Glama rebuild — factual updates are safe now; the
MandalaOS feature page waits for §7.

**Done 2026-09-13 night (this track):** step-0 policy contract live
(lakshmi `78f3c8b`); `telemetry.record` observation kind + typed rollups
(whitemagic `38bf66e`, clippy `31eafd2` — rides v9.1.5); VM daemon
either/or cleanup (sovereign `93bc3c2`); host wrapper + fleet wiring
(sovereign `2d56146`); telemetry repointed to the fleet gateway
(lakshmi `39dffd3`); signing-key off-machine backup (SD_CARD1 + paper
passphrase).

**Done 2026-09-14 early (this track):** `telemetry.retention` read-only
planner (whitemagic `main`) + weekly `wm-telemetry-retention.timer`
installed; live-verified against the 9.1.4 gateway (script degrades
gracefully, prune ran) and scratch-store E2E (planner shape; wet prune
dharma-vetoed under load as designed). `landrun-sandbox` pure-Landlock B2
runner (sovereign `scripts/`, packaged + wired: daemon keeps
`WM_LANDLOCK=1` and routes spawns through it); **in-guest matrix 13/13
green** on the rebuilt VM (`v5kjrw43…`), including nested-under-Landlock
works / bwrap-blocked-under-Landlock.

**Done 2026-09-15 (this track):** S4 executed in the rebuilt VM (585-drv
rebuild, kernel 6.18.50, `wm 9.1.5`; Tetragon bundle hand-installed with
`--bpf-lib`; collector sent 3 records; `shadow.access.v1` → `observing`);
bridge read path became mirror-first (LAKSHMI `6cc03f6` pushed: sent-log
merge + value summing; SOVEREIGN `98f0e30` pushed: feed ring); Y1 actuator
contract written; packaging version derived from `Cargo.toml` (was hardcoded
`9.1.3`); fleet sampler restarted onto the new read path (edge soak
untouched). Original-notes alignment annex in §9.

**Done 2026-09-15 (later):** routine capture tooling —
`SOVEREIGN/scripts/capture_window.sh` (one-command instrumented window with
a GC-rooted VM build) and `LAKSHMI/bridge_report.py` (per-policy decisions,
inputs, false-positive candidates). First scripted run: 72 events → 4 records,
0 spooled, `shadow.access.v1` cycled observing→clear, 0 false-positive
candidates. Y1.0 actuator router (notify-only) shipped in LAKSHMI `84f2b49`;
WMv9 `ActuationNotify` event type + `wm doctor` bridge line (`a025b34`,
`979fe54`, rides 9.1.7); sovereign pin bumped to v9.1.6 (`2f3a07a`).

**Done 2026-09-15 (moves 1–3):** routine captures live (script + report,
first run green); stranger-install dry run found 6 gaps, 5 fixed in
`GETTING_STARTED` (§0 checklist: your key, your disk path; correct
`mandala-vm` build; installed-Nix commands; counts/roadmap synced) with 2
documented prototype edits still disclosed in
`publication/STRANGER_INSTALL_PROTOCOL.md` §8; Y1.1 subject capture shipped
(`proc:`/`tool:`/`dim:` subjects flow collector → records → dashboard).

---

## 9. Annex — original-notes alignment (2026-09-15)

Lineage check against the 2025 corpus (`design/---MandalaOS.txt` — parts I–IV
plus the Qubes/eBPF/SutraCode staging; the 2025-05-26 Concept Review; the
2026-04 NixOS vision spec; `realization/MandalaOS_v0.1_SPEC.md`). Statuses are
the ones §1 verifies; this annex maps *intent* only.

| Original pillar | Current realization | State |
|---|---|---|
| Bindu microkernel; in-kernel Tiferet/Lakshmi | Linux 6.18/NixOS + systemd substrate; Landlock LSM + bwrap/landrun runner as enforcement seam | Gated research; form deliberately changed (PLATFORM_DIRECTION §2) |
| Ganas as user-space services (Vayu/Akasha/Prithvi/IndraNet/Maya) | OS-layer functions delegated to NixOS/systemd; WM's 28-gana layer covers governance; GanYingBus + mesh locks stand in for IndraNet | Re-mapped, not re-implemented |
| Lakshmi / Harmony Vector | `feasibility/harmony-vector-spec.md` → live digestor, telemetry galaxy, dashboard `:3109`, Samma-Meter + Policies panel | Strongest alignment |
| Tiferet self-balancing | Step-0 policies live with the full hysteresis contract (`design/ACTUATION_HYSTERESIS_2026-09-13.md`); ladder steps 1–4 design-only | Observe-only by design; no closed loop |
| Yama / Dharma Engine (Gevurah–Chesed) | Observe-first bridge S1–S4 (bus events, Tetragon collector, Lakshmi policies); enforcement seam proven, unwired; explain-first in dashboard | Correctly sequenced; blocking deferred |
| Karma ledger / mandatory effects | Typed debt accounting + Phase A `EffectRow` (Rust); declared-vs-actual writes; SutraCode unbuilt | Matches the notes' own research-grade verdict |
| Gnosis Portals / Anti-Maya | `gnosis`/`capabilities`/explain-this; `design/GNOSIS_PORTAL_UI_2026-09-14.md` plans the per-layer mirror (living Mandala, ≤3 clicks to a record) | Active |
| Maya UI / Reflection of State (Lila/Ziran); Stoic cards; Sankey | Living-Mandala P0 + canvas layer (mood aurora, flow motes, vibrancy); Stoic/Samma/explain lifted from the Concept Review | Active; Sankey P3 |
| Attestation / supply chain | Signed releases, custody register (4 copies, chain proven), reproducible NixOS; no TPM measurement or SLSA claim | Partial, disclosed |
| Compartmentalization form | Qubes → NixOS VM + namespaces/LSM; claim discipline "containment of tool/agent behavior, never Qubes-level" | Deliberate divergence (QUBES_PATH_ASSESSMENT) |
| Ecosystem hooks (MandalaMesh/Sense/Craft/Ledger, layered AI strata, Welcome Dojo, MandalaLite) | Not built; DEVICE_SYNC is the nearest neighbor | Unstarted; Sci-Fi World integration deferred |

**Deliberate divergences (documented, not drift):** Qubes-first staging
replaced by the Sovereign VM; kernel-level interception replaced by LSM/eBPF
observe + user-space runner; mandatory effect language replaced by Rust effect
types + karma ledger; the operative spec is the 2026-04 NixOS vision, with the
2025 nanokernel kept as lineage and metaphor (it survives in the UI: Bindu as
the mandala's center).

**Concept Review recommendations — closed:** Harmony Vector spec (live);
"prototype the Lakshmi dashboard first" (shipped + living Mandala); minimum
Dharma ruleset (observe policies incl. the bridge trio); explain-first /
coercion-free UX (explain lines, Samma-Meter, Stoic cards); public repo and
gates (WM public; sovereign/page still behind §7 — edge-galaxy soak fires
~Sep 16 23:36Z).

**Still open from the originals:** SutraCode + effect taxonomy; OS-level
default-deny egress; `mandala-ctl`; TPM attestation;
MandalaMesh/Sense/Craft/Ledger; layered-AI trust strata (L−1…4); Ubuntu
"neighbour-view"; and the **Mandala Glossary** (one name per subsystem) the
Concept Review asked for and that still does not exist.

**Verdict:** the substance (Dharma, Karma, Lakshmi, Gnosis, explain-first,
observe-before-enforce) survived the form change. The 2025 nanokernel/Qubes
path is now explicit gated lineage, not the build route; the live route is
the 2026-04 spec (declarative NixOS host for governed agent workloads) with
the Yama bridge as its first native subsystem.
