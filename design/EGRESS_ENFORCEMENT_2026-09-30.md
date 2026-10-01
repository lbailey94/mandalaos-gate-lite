# Egress enforcement — current truth and the destination-allowlist path

**Status:** design note and vocabulary correction, 2026-09-30. It changes no
runtime containment beyond receipt vocabulary; no qualified destination
enforcement exists yet. Companion correction: gate-lite receipts now carry a
per-entry `"enforced"` flag and state the granted scope as whole-network
(`gate-lite/gate_lite/orchestrator.py`, `gate-lite/README.md`).

## What is true today (0.4 lane)

- Default deny: without `net: true` and declared destinations, the wrapper
  runs `bwrap --unshare-all` (no network); the denial is recorded in
  `task.execution.egress` with `"enforced": true`.
- Granted egress: `net: true` plus a declared list grants the **whole
  network** (`bwrap --share-net` plus resolver/CA binds). The declared
  destinations are recorded intent — they are an audit list, not an
  allowlist — and now carry `"enforced": false` so no reader can mistake the
  entry for destination-level enforcement.
- The wrapper envelope (`wm-sandbox-exec-v1`) only carries `net`; it never
  receives the declared list, so nothing at the target could enforce it.

## Why this matters

The governed-workspace promise is "state exactly what it may do." For
strangers running arbitrary code on a shared kernel, granting whole-network
access is the largest remaining capability gap after filesystem containment:
exfiltration, proxying, and scanning are all reachable once any host can be
contacted. A `TRUSTED` receipt must not imply otherwise; hence the correction
above is a truth fix independent of when enforcement lands.

## Options for destination-level enforcement

| # | Approach | Strengths | Costs / risks |
|---|---|---|---|
| A | Per-slot netns + veth + nftables allowlist with DNS pinning (root/systemd) | Kernel-level, works for any protocol | Domain→IP pinning breaks CDNs/rotation; needs root; DNS complexity |
| B | Per-slot netns + nft REDIRECT into a filtering proxy; allowlist by SNI/Host (CONNECT) | No MITM needed for host allowlisting; TLS passthrough; testable | HTTP(S)-only; every flow must be forced through the proxy; proxy failure must fail closed |
| C | microVM / gVisor tier with host-side egress policy | Real isolation boundary; clean policy point | Separate tier; not the current bwrap profile |
| D | Keep whole-network grants, record `"enforced": false`, require explicit operator opt-in per pass | Zero new mechanism; honest | Not suitable for untrusted tenants |

## Recommendation

1. **Now:** option D with the vocabulary correction that landed 2026-09-30.
   Any granted-egress pass remains an operator decision, and receipts say
   exactly what was enforced.
2. **Next qualified profile:** option B on the bwrap lane — a per-slot
   filtering proxy with fail-closed behavior — using a no-network namespace and a host-side proxy over a narrowly
   exposed Unix socket. A `--share-net` wrapper alone cannot prevent proxy
   bypass. Qualification must test raw-network refusal and proxy-only
   access on the exact profile. Option A is a fallback for
   fixed endpoints; option C belongs to the microVM track.
3. A profile may only claim `"enforced": true` with an enforcer id when the
   acceptance suite below passes on the host where it runs.

## Acceptance criteria for a future qualified egress profile

1. Allowed host reachable; an unlisted host fails, with the denial recorded.
2. DNS cannot be used to reach unlisted destinations (rebinding/pinning
   attempt fails).
3. Proxy/runtime failure denies egress rather than falling back to an open
   network, and the failure is recorded.
4. The receipt records the enforcement mode truthfully (`"enforced": true`
   plus an enforcer identifier) and the qualified runner profile digest.
5. The G3 denial cases still pass unchanged; the 0.4 lane remains the
   default profile until a candidate is reviewed.
