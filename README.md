# MandalaOS — gate-lite 0.5 review candidate

Status: local selective port prepared for independent review, 2026-10-09.
Public main at `75ebbd6d9fd96bc2b6b33e939970449be97027f3` remains the 0.4
review snapshot until this port is reviewed and published. This repository
contains one slice of MandalaOS; it is not a release of the whole system.

Gate-lite issues governed passes to cooperating agents, supervises a bounded
execution, and emits signed Continuity Receipts. It exposes a CLI and MCP
stdio or loopback HTTP. Project site: https://www.whitemagic.dev.

## Source and evidence boundaries

This candidate selectively ports the accepted private source
`8e84b2520b535d1452d4966d885411ee7aaea47d` onto public main `75ebbd6…`.
It preserves the public lifecycle and egress behavior and the historical signed
evidence. The receipt dependency is exactly `continuity-receipt==0.5.0`;
startup checks distribution metadata, imported runtime version, and spec support
before creating state. The verifier is installed from PyPI, not vendored.

The accepted private frozen-source exercise fetched that pushed source and the
complete public wrapper packet at
`1357c147410e2471872cb0658d93199457461e65` separately. Its seven-receipt bundle
verified TRUSTED; independent recomputation checked commitment, invocation,
wrapper, stdout and issuer delivery bindings. Clean and configured suites each
passed 131 tests with 6 explicit skips; real Bubblewrap acceptance passed 10
with 2 quota skips; wrapper argv tests passed 6. That is bounded same-host
reproduction by collaborators. It does not qualify another host or establish
that this selective public port has passed review. The preserved capture and
its limits are in [the evidence report](gate-lite/evidence/frozen-source-2026-10-09/REPORT.md).

The port's own exact-commit checks are recorded separately during review.
Independent port review and the publication decision remain open. The earlier
October 8 capture at `8ea8c7e` remains local-reviewed, pre-push; it is not
relabeled as the later frozen-source exercise. Historical 0.3 and 0.4 bundles,
raw transcripts, and the committed 0.4 vectors retain their original bytes and
labels.

## What the candidate changes

- New bundles use `continuity-receipt/0.5`, including a `state.commitment`
  over the exact registry snapshot consumed by the commitment method.
  Commitment failure after execution leaves a visible `receipt_incomplete`
  hold rather than a retryable success.
- Real execution accepts only the reviewed `bwrap-v1` wrapper and exact
  Bubblewrap/jq identities. Unknown or changed identities fail before token
  consumption or payload spawn. The profile reports `locally_qualified` and
  `bwrap`; it establishes neither Landlock nor a VM boundary.
- CLI token input supports `--token-stdin`. Preflight failures are structured
  through CLI and MCP. Settlement after restart binds the issuer's delivery
  response to the persisted execution stdout digest. A pre-execution settlement
  retains the explicit `sha256("none")` sentinel.
- Ordinary tests isolate ambient runner settings. Real-runner acceptance and
  wall/OOM quota drills each require explicit opt-in. Vector generation uses
  an explicit spec and a separate output directory; it cannot overwrite the
  committed historical corpus.

## Run and review

From the repository root, with Python 3.11+:

```bash
python3 -m venv .venv
.venv/bin/pip install -e gate-lite
.venv/bin/pip check
cd gate-lite
../.venv/bin/python -m unittest discover -s tests -v
../.venv/bin/python tools/test_sandbox_argv.py -v
../.venv/bin/continuity-receipt-verify vectors/02_happy_full.json
../.venv/bin/continuity-receipt-verify evidence/frozen-source-2026-10-09/bundle-task.json
```

The vectors command above checks historical 0.4 compatibility. The captured
0.5 bundle is evidence for its private source pin, not proof of current port
execution. Use [protocol v2](GATE_LITE_OUTSIDER_EXERCISE.md) to exercise a fresh,
exact source export and capture new evidence. CLI/MCP examples and opt-ins are
in [gate-lite/README.md](gate-lite/README.md); adapter requirements are in
[INTEGRATION_CONTRACT.md](gate-lite/INTEGRATION_CONTRACT.md).

The MIT wrapper packet is publicly available at
[gate-lite/runners/bwrap-v1](gate-lite/runners/bwrap-v1/README.md). Its executable
SHA-256 is `f7da8d6c3809ac5adbc4631c82fb9327abdb69638715bb0ea1493dc79996411e`.
The complete exercised packet commit is `1357c147…`; tag `bwrap-v1-packet` is a
convenience reference. That packet's private-upstream boundary and attribution
stay intact. Host Bubblewrap and jq builds must also match the reviewed profile;
changing builds requires a new reviewed profile.

## Limits

This is shared-kernel Bubblewrap containment for cooperative workloads.
`--demo` is explicit simulation and receipts use class `none`. Egress is
network-isolated by default. Granting `net: true` with declared destinations
shares the whole network; the destinations describe intent and carry
`enforced: false`. Destination-level enforcement and the separate L2 proxy
profile are outside this port.

TRUSTED checks the signed chain and protocol/policy consistency. It does not
prove issuer honesty, actual containment, or factual delivery. The issuer's
stdout binding is not an external delivery attestation, and a $0 invoice flow
is not payment qualification. Wall/OOM quota qualification, independent
adoption, payment qualification, external delivery attestation, hostile-tenant
isolation, and VM containment remain open. Older dogfood and benchmark results
apply to their historical environments.

## Project and licensing boundaries

[Continuity Receipt](https://github.com/lbailey94/continuity-receipt) is the
separate Apache-2.0 receipt format and reference implementation.
[WhiteMagic](https://github.com/lbailey94/whitemagic) provides memory and
governance. Neither requires gate-lite. The Sovereign and Lakshmi repositories
remain private; this snapshot does not distribute them. Repository code is MIT;
the wrapper uses its adjacent packet-scoped MIT license. See [NOTICE.md](NOTICE.md).

The human maintainer, Lucas Bailey, is accountable for the content. AI
collaborators worked under his direction; implementation and claims remain
subject to review. Start with [REVIEW_NOTES.md](REVIEW_NOTES.md) for the review
map. Older dated design and status documents describe their recorded scopes;
this README describes the candidate under review.
