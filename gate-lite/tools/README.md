# Gate-lite runner qualification probes

`qualify_bwrap_runner.py` is a bounded, fixed-payload candidate probe for the
portable `mandala-sandbox` wrapper. It accepts no payload argument. The only
work executed through the wrapper is its fixed probe, which compares network
and mount namespace identities, verifies the `/workspace` read-only bind,
attempts a write there, and checks that `/tmp` is a writable tmpfs. Its test
workspace is temporary; the intended denied write leaves no host artifact.

The pinned wrapper bytes are published in this repository at
`gate-lite/runners/bwrap-v1/` (MIT packet; acquisition ref `bwrap-v1-packet`,
verify with `sha256sum -c SHA256SUMS`). The default path and digest below
remain the rehearsal values.

Run it from the gate-lite directory:

```sh
python3 tools/qualify_bwrap_runner.py \
  --expected-bwrap-sha256 sha256:<independently-reviewed-bwrap-digest>
```

The default wrapper path and digest are the rehearsal values recorded in
`design/RUNNER_CLASS_CLOSURE_PLAN_2026-09-25.md`. The probe resolves and hashes
both executables, checks optional expected digests, captures the wrapper's
exact Bubblewrap argument tokens through a temporary forwarding shim, and
rechecks both identities after execution. Evidence is JSON on stdout; exit
status is nonzero when identity or probe checks fail. If
`--expected-bwrap-sha256` is omitted, the observed Bubblewrap hash is recorded
but its identity is marked unpinned; a human must review provenance before
using the observation as candidate evidence.

`probe_status: PASS` only means the listed checks passed with the identified
executables on this host; it is a technical probe result, not qualification or
closure. The expected Bubblewrap digest must come from independent provenance
review. The
result always leaves `classification_status` and `conclusion` as `OPEN`. The
network check compares namespace identities; it does not attempt outbound
connections or prove that every route is denied. The evidence is not a signed
receipt, does not qualify a receipt class, and does not satisfy the separate
independent-host adoption gate.

Focused adversarial tests use fake wrapper and Bubblewrap executables and never
invoke the host runner:

```sh
PYTHONPATH=.venv/lib/python3.12/site-packages \
  .venv/bin/python -m pytest tests/test_qualify_bwrap_runner.py -q
```
