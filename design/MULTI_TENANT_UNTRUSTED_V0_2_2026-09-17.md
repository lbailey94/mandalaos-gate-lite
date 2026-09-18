# Multi-Tenant / Untrusted v0.2 — Decisions and Qubes-Like Path

**Status:** decision draft for Lucas — nothing here is committed work.
**Date:** 2026-09-17. **Companions:** `CURRENT_REALITY_2026-09-13.md` §2,
`PLATFORM_DIRECTION_2026-09-12.md` §2–3, `THREAT_MODEL.md`, market evidence in
`WHITEMAGIC/planning/MARKET_UPDATE_2026-09-17.md` §3.
**Origin:** strategy thread — "can agents spin up mandalas for micropayments?"
The blocker named there was exactly this: current containment is a shared-kernel
trust class; selling to *untrusted* tenants requires a hardware boundary.

---

## 1. Where we actually stand (no overclaim)

- Shipped: NixOS sovereign VM, bwrap/Landlock runners, 13/13 in-guest matrix,
  daemon + read-only MCP, Tetragon observe, Yama v0 (observe-first).
- Claim discipline (`PLATFORM_DIRECTION` §2): *containment of tool/agent
  behavior — the browser-sandbox trust class*. **Not** kernel-exploit-safe,
  **not** a hostile local user boundary, **not** Qubes-level.
- Therefore: **today we may host our own agents and cooperative users; we may
  not host adversarial tenants.** Any paid "mandala for an agent" SKU before
  v0.2 would overclaim exactly the thing the record has been correcting.

Market context that de-risks the decision: the entire agent-sandbox category
prices the **untrusted** case on hardware virtualization (Firecracker-class;
E2B 1B+ sandboxes / 94% of F100), with gVisor as the acknowledged middle and
shared-kernel containers rejected as the floor. Buyers already understand the
ladder. We do not need to educate; we need to sit on the correct rung.

## 2. The decisions to make (v0.2 scope)

| # | Decision | Options | Notes |
|---|---|---|---|
| D1 | Isolation primitive per untrusted mandala | (a) microVM (KVM: Cloud Hypervisor/Kata/Firecracker) (b) gVisor (c) namespace+LSM status quo | (a) is the recommended floor; (c) stays for cooperative workloads only |
| D2 | Tenancy model | (a) dedicated host per customer (b) multi-tenant host, one microVM per mandala | (a) first — simplest honest claim; (b) after measured soak |
| D3 | Mandala lifecycle | create/exec/status/snapshot/fork/destroy | `mandala-ctl` per original spec; snapshot persistence is table stakes in the market |
| D4 | Resource governance | per-mandala cgroup quotas, disk caps, pass time-box | hard caps enforced outside the guest (economic firewall + cgroup) |
| D5 | Egress | default-deny, per-mandala allowlist, logged | spec'd in the vision; must move into the microVM-era config |
| D6 | Data at rest | per-mandala volumes; keys per Q39 keyring design | ties to Q39 S4 slice A (wrapped DEKs, RK mode B/C) |
| D7 | Identity/delegation | `agent:<id>/tool:<t>`, `delegation:<principal>→<agent>`, `wallet:<authority-scope>` | the WhiteMagic↔MandalaOS seam; needed for billing and attribution |
| D8 | Billing gate | invoiced keys primary; x402 per-pass optional; pass token signed | never load-bearing; same doctrine as hosted recall |
| D9 | Abuse/refusal policy | published AUP; refusal at creation (Dharma economic profile) + kill/rollback | mining/spam/proxying are explicit refusal classes |
| D10 | Attestation | signed config manifest per mandala; host measurement where available | needed for enterprise assurance claims; keep "no TPM claim" until TPM ships |

## 3. Qubes-likeness — what to copy without Xen

Qubes' durable ideas are structural, not hypervisor-bound. Mapping:

| Qubes concept | MandalaOS equivalent | State |
|---|---|---|
| dom0 (trusted admin) | sovereign host: systemd + governance services | exists |
| App qube (disposable) | microVM per agent mandala (D1a), disposable by default | missing (this doc) |
| Template qube | content-addressed mandala template (Nix closure + WM store snapshot) | partially: Nix closures exist; template lifecycle doesn't |
| qrexec (service channel) | GanYingBus / MCP + mesh transport; per-mandala policy at the boundary | partial (transport exists; cross-VM channel not wired) |
| Per-qube firewall | per-mandala egress proxy with allowlist + logging | spec'd, missing |
| Inter-VM copy/paste, per-qube storage | per-mandala writable volume + explicit transfer verbs | missing |
| Disposable VMs | pass token = time-boxed disposable mandala, destroy on expiry | missing; pricing primitive already spec'd (private economics) |

**Honest ceiling:** without a Type-1 hypervisor and VT-d, this is
"Qubes-inspired compartmentalization with KVM microVMs on a shared NixOS host."
It is weaker than Qubes (no dom0 separation by hypervisor, no graphics
isolation) and stronger than the current sovereign form for untrusted tenants
(hardware boundary per mandala). Say exactly that; never "Qubes-level."

## 4. Candidate architecture (v0.2 target)

```
NixOS sovereign host (existing)
├── governance core: wm-governance + karma ledger + dharma (existing)
├── mandala-orchestrator (new): lifecycle over KVM microVMs
│   ├── template store: Nix closure + WM store image (content-addressed)
│   ├── per-mandala: cgroup v2 quota, default-deny egress proxy, encrypted volume
│   └── receipts: create/exec/snapshot/destroy → signed record + karma entry
├── microVM classes:
│   ├── kata/cloud-hypervisor (recommended first: OCI-compatible, ARM-capable)
│   └── firecracker (later: smallest overhead, strongest market precedent)
└── WhiteMagic inside each mandala: same binary, read-only or scoped store
```

Why Kata/Cloud Hypervisor first over Firecracker: OCI/CRI compatibility and
easier Nix packaging; Firecracker's jailer + rootfs pipeline is more bespoke
for a solo operator. Both satisfy the hardware-boundary floor. Revisit if boot
latency targets require it (Firecracker <150ms vs Kata ~200–500ms).

## 5. Acceptance tests (must pass before any untrusted tenant)

1. Escape probes inside a mandala (kernel-exploit sim, `/dev/kvm` abuse,
   metadata-service probes, DNS exfiltration) — no host or cross-mandala reach.
2. Resource: cgroup quota enforced; CPU/mem/disk overrun kills the mandala,
   not the host.
3. Egress: undeclared destination denied and recorded; allowlist honored.
4. Storage: per-mandala volume does not decrypt outside its mandala; destroy
   provably erases key material (Q39 erasure semantics).
5. Rollback: host snapshots + restore a mandala after induced corruption.
6. Receipts: create/exec/destroy each produce a verifiable record in the karma
   chain; billing evidence reconstructable from records alone.
7. Load: N concurrent passes on one host with latency/overhead budget measured
   (baseline: current VM 390Mi idle / 3.8Gi host; microVM overhead target
   ≤5 MiB per instance per Firecracker precedent).
8. Claim audit: THREAT_MODEL.md updated with the microVM boundary and the
   disclosed deltas (no TPM, no dom0 separation, no GPU isolation).

## 6. Proposed sequencing (gated, no code tonight)

1. **Now–v9.1.x:** hosted recall beta (invoiced keys) + machine-native services
   behind x402 (continuity.restore / backup.store / index.verify / benchmark.run).
   Economic firewall + run-scoped budgets + receipts ship with this lane.
2. **v0.2 planning gate:** choose D1 (recommend Kata/Cloud Hypervisor),
   D2=a (dedicated host per customer), and write the orchestrator contract
   (ACTUATOR_CONTRACT pattern) before implementation.
3. **v0.2 build slice 1:** `mandala-ctl up/status/destroy` on one template, one
   tenant, acceptance tests 1–4.
4. **v0.2 slice 2:** snapshot/fork + pass token + billing gate (acceptance 5–7).
5. **Qubes track stays gated** on funding + hardware (unchanged per
   PLATFORM_DIRECTION §6.1); nothing here reopens it.

## 7. Open questions for Lucas

- Q1: Is the first untrusted tenant class "agents we can charge" or
  "cooperative partners we onboard manually"? (Recommend: partners first —
  validates lifecycle without abuse exposure.)
- Q2: Do we sell a *hosted* mandala at all, or ship the orchestrator as part
  of the open Sovereign image and let operators run the paid lane? (Open-core
  promise: image open; hosted governed lane paid.)
- Q3: Does the pass token become a first-class MCP tool (`mandala.pass`), or
  stay a hosted-lane SKU with no tool surface? (Recommend: tool surface, since
  agents are the buyers.)
- Q4: Which identity for buyers first — did:web or API key + principal DID
  claim? (Recommend: key first, DID claims recorded not verified.)
