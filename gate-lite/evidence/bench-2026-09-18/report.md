# Gate-lite benchmark report

- Profile: **standard** · recorded 2026-09-18T02:52:38Z
- Host: Intel(R) Core(TM) i5-8350U CPU @ 1.70GHz · 8 threads · 15867 MB RAM · kernel 7.0.0-31-generic
- Python 3.12.3 · bubblewrap 0.9.0 · systemd 255 (255.4-1ubuntu8.17)
- Runner: `~/.local/bin/mandala-sandbox` · load avg at start [5.0927734375, 7.0595703125, 6.16015625]

Method: warmup, auto-calibrated n against a per-case time budget; latency
percentiles are over per-operation samples. Percentiles on low-n latency
cases (snapshot, kill, OOM) are indicative, not distribution-grade.

## A

| Case | n | median | p95 | p99 | mean | sd | min | max | per sec |
|---|---|---|---|---|---|---|---|---|---|
| canonicalize body (small, ~0.3 KB) | 2000 | 0.01 ms | 0.0206 ms | 0.0321 ms | 0.0114 ms | 0.0068 ms | 0.0098 ms | 0.2021 ms | 87373.52 |
| canonicalize body (large, ~20 KB) | 781 | 0.7159 ms | 1.0873 ms | 1.3853 ms | 0.7737 ms | 0.1419 ms | 0.6793 ms | 1.7032 ms | 1292.54 |
| commit_field (small body) | 2000 | 0.0132 ms | 0.0321 ms | 0.0587 ms | 0.0168 ms | 0.009 ms | 0.0123 ms | 0.1006 ms | 59663.1 |
| sign_receipt (Ed25519) | 2000 | 0.0654 ms | 0.1091 ms | 0.1588 ms | 0.0718 ms | 0.0172 ms | 0.0611 ms | 0.234 ms | 13937.11 |
| verify bundle (6 receipts) | 494 | 1.2611 ms | 1.7883 ms | 2.4292 ms | 1.3537 ms | 0.2418 ms | 1.1754 ms | 3.1073 ms | 738.74 |
| verify bundle (100 receipts) | 36 | 22.2414 ms | 25.4789 ms | 28.4382 ms | 22.6371 ms | 1.5553 ms | 20.774 ms | 28.4382 ms | 44.18 |
| build chain (100 receipts) | 57 | 13.8843 ms | 16.3114 ms | 16.8872 ms | 14.2342 ms | 1.0552 ms | 12.6898 ms | 16.8872 ms | 70.25 |
| verify tampered bundle (100 receipts) | 34 | 23.6017 ms | 29.8399 ms | 30.7521 ms | 23.974 ms | 1.876 ms | 21.9015 ms | 30.7521 ms | 41.71 |

## B

| Case | n | median | p95 | p99 | mean | sd | min | max | per sec |
|---|---|---|---|---|---|---|---|---|---|
| get_slot (100 slots) | 1278 | 0.3719 ms | 0.6399 ms | 0.7963 ms | 0.4064 ms | 0.0915 ms | 0.357 ms | 1.2487 ms | 2460.65 |
| put_slot (100 slots) | 342 | 2.3782 ms | 3.6112 ms | 5.4713 ms | 2.8583 ms | 3.3428 ms | 2.1767 ms | 46.8917 ms | 349.86 |
| recall miss (100 slots) | 2000 | 0.3757 ms | 0.5513 ms | 0.7484 ms | 0.401 ms | 0.0754 ms | 0.3585 ms | 1.0136 ms | 2493.68 |
| get_slot (1000 slots) | 159 | 4.4513 ms | 6.1878 ms | 6.8492 ms | 4.7092 ms | 0.8896 ms | 3.7192 ms | 11.8773 ms | 212.35 |
| put_slot (1000 slots) | 28 | 27.2351 ms | 31.9798 ms | 34.3089 ms | 27.6294 ms | 2.2978 ms | 24.2748 ms | 34.3089 ms | 36.19 |
| recall miss (1000 slots) | 212 | 3.9772 ms | 5.3406 ms | 6.6595 ms | 4.17 ms | 0.7152 ms | 3.5191 ms | 10.2003 ms | 239.81 |
| get_slot (10000 slots) | 18 | 43.2313 ms | 53.5319 ms | 53.5319 ms | 43.259 ms | 3.5071 ms | 38.36 ms | 53.5319 ms | 23.12 |
| put_slot (10000 slots) | 10 | 314.6001 ms | 351.1382 ms | 351.1382 ms | 311.791 ms | 31.2342 ms | 238.6225 ms | 351.1382 ms | 3.21 |
| recall miss (10000 slots) | 18 | 42.6904 ms | 49.1377 ms | 49.1377 ms | 43.5575 ms | 3.0443 ms | 39.1065 ms | 49.1377 ms | 22.96 |

## C

| Case | n | median | p95 | p99 | mean | sd | min | max | per sec |
|---|---|---|---|---|---|---|---|---|---|
| full flow (pass/exec/settle/terminate) | 98 | 14.727 ms | 24.4751 ms | 66.8125 ms | 16.7046 ms | 8.3037 ms | 8.0537 ms | 66.8125 ms | 59.86 |
| flow without settlement (3 receipts) | 41 | 23.4155 ms | 26.3376 ms | 72.7966 ms | 24.2515 ms | 8.0962 ms | 18.8325 ms | 72.7966 ms | 41.23 |
| idempotent replay (pass+exec) | 179 | 3.7409 ms | 5.4484 ms | 7.5694 ms | 3.9328 ms | 0.725 ms | 3.1964 ms | 8.453 ms | 254.27 |
| sweep 500 expired slots (fresh batch) | 3 | 6601.9278 ms | 6852.3199 ms | 6852.3199 ms | 6684.09 ms | 145.7044 ms | 6598.0224 ms | 6852.3199 ms | 0.15 |
| snapshot workspace 1 MB | 5 | 40.7719 ms | 41.0867 ms | 41.0867 ms | 40.5681 ms | 0.4984 ms | 39.851 ms | 41.0867 ms | 24.65 |
| restore workspace 1 MB | 5 | 10.2253 ms | 10.9631 ms | 10.9631 ms | 10.2869 ms | 0.4047 ms | 9.9349 ms | 10.9631 ms | 97.21 |
| snapshot workspace 10 MB | 5 | 450.0164 ms | 511.1932 ms | 511.1932 ms | 445.4321 ms | 45.9086 ms | 387.2159 ms | 511.1932 ms | 2.25 |
| restore workspace 10 MB | 5 | 101.8185 ms | 108.0062 ms | 108.0062 ms | 102.8042 ms | 4.5354 ms | 96.9293 ms | 108.0062 ms | 9.73 |
| snapshot workspace 50 MB | 3 | 2017.1786 ms | 2128.3817 ms | 2128.3817 ms | 2027.7224 ms | 95.8234 ms | 1937.607 ms | 2128.3817 ms | 0.49 |
| restore workspace 50 MB | 3 | 509.7269 ms | 518.6014 ms | 518.6014 ms | 498.722 ms | 27.1122 ms | 467.8377 ms | 518.6014 ms | 2.01 |
| list_ tenant slots (10k registry) | 16 | 42.0828 ms | 49.2467 ms | 49.2467 ms | 43.0015 ms | 2.8377 ms | 40.1466 ms | 49.2467 ms | 23.26 |

## D

| Case | n | median | p95 | p99 | mean | sd | min | max | per sec |
|---|---|---|---|---|---|---|---|---|---|
| raw wrapper exec (bwrap, echo) | 29 | 27.7603 ms | 30.4872 ms | 33.3643 ms | 27.9166 ms | 1.7488 ms | 25.5713 ms | 33.3643 ms | 35.82 |
| gate exec via SandboxRunner (echo) | 20 | 34.5752 ms | 37.5137 ms | 39.0763 ms | 34.9425 ms | 1.574 ms | 32.2247 ms | 39.0763 ms | 28.62 |
| gate exec via SliceRunner (echo) | 10 | 96.706 ms | 106.7106 ms | 106.7106 ms | 96.8439 ms | 4.8223 ms | 89.894 ms | 106.7106 ms | 10.33 |
| operator kill latency (sleep payload) | 10 | 50.9756 ms | 1109.8601 ms | 1109.8601 ms | 463.9564 ms | 533.4972 ms | 50.8448 ms | 1109.8601 ms | 2.16 |
| OOM quota-seal latency (memory hog) | 5 | 162.0051 ms | 170.2106 ms | 170.2106 ms | 158.6508 ms | 12.6239 ms | 137.0054 ms | 170.2106 ms | 6.3 |
| egress-denied curl exec | 22 | 34.21 ms | 38.2774 ms | 39.2182 ms | 34.5959 ms | 2.0591 ms | 32.2266 ms | 39.2182 ms | 28.91 |

## E

| Case | n | median | p95 | p99 | mean | sd | min | max | per sec |
|---|---|---|---|---|---|---|---|---|---|
| HTTP keep-alive ping | 2000 | 0.4182 ms | 0.5764 ms | 0.8185 ms | 0.423 ms | 0.0948 ms | 0.2748 ms | 1.3073 ms | 2364.11 |
| HTTP keep-alive status | 1477 | 0.5526 ms | 0.7611 ms | 1.0367 ms | 0.5846 ms | 0.108 ms | 0.4412 ms | 1.7175 ms | 1710.62 |
| HTTP per-connection ping (urllib) | 938 | 0.858 ms | 1.3311 ms | 1.6702 ms | 0.9047 ms | 0.2081 ms | 0.6017 ms | 2.4063 ms | 1105.39 |
| HTTP concurrent ping (8 clients x 50) | 400 | 4.2725 ms | 7.9191 ms | 11.496 ms | 4.5246 ms | 2.1283 ms | 0.4322 ms | 13.5349 ms | 221.01 |
| stdio ping | 2000 | 0.0419 ms | 0.0813 ms | 0.118 ms | 0.0486 ms | 0.0196 ms | 0.0314 ms | 0.2298 ms | 20570.33 |
| stdio status | 2000 | 0.1202 ms | 0.2313 ms | 0.2882 ms | 0.1413 ms | 0.0459 ms | 0.107 ms | 0.7152 ms | 7079.2 |
| full lifecycle over stdio | 10 | 5.5815 ms | 7.7295 ms | 7.7295 ms | 5.9306 ms | 0.9211 ms | 4.8339 ms | 7.7295 ms | 168.62 |
| full lifecycle over HTTP keep-alive | 10 | 6.9325 ms | 8.9682 ms | 8.9682 ms | 7.0364 ms | 1.0507 ms | 5.8322 ms | 8.9682 ms | 142.12 |

## F

| Case | n | median | p95 | p99 | mean | sd | min | max | per sec |
|---|---|---|---|---|---|---|---|---|---|
| soak flow latency (300 flows) | 300 | 28.0188 ms | 52.5175 ms | 58.1148 ms | 30.145 ms | 24.0876 ms | 3.6267 ms | 357.1504 ms | 33.17 |

## Metrics & sizes

| Group | Metric | Value | Unit |
|---|---|---|---|
| A/sizes | receipt compact bytes (pass) | 595 (595 B) | bytes |
| A/sizes | receipt compact bytes (decision) | 741 (741 B) | bytes |
| A/sizes | receipt compact bytes (termination) | 538 (538 B) | bytes |
| A/sizes | bundle compact bytes (6 receipts) | 5527 (5.4 KB) | bytes |
| A/sizes | bundle stored bytes (6 receipts, indent=2) | 7429 (7.3 KB) | bytes |
| A/sizes | bundle compact bytes (pass+termination) | 1679 (1.6 KB) | bytes |
| A/sizes | receipts per task (full flow) | 6 | count |
| B/sizes | state.json bytes (100 slots) | 43460 (42.4 KB) | bytes |
| B/sizes | state.json bytes (1000 slots) | 432260 (422.1 KB) | bytes |
| B/sizes | state.json bytes (10000 slots) | 4320260 (4.1 MB) | bytes |
| B/parallel | parallel pass writers (4 workers x 5) | 684.96 | ms wall |
| B/parallel | parallel pass writers (8 workers x 5) | 1550.49 | ms wall |
| B/parallel | parallel pass writers (16 workers x 5) | 3694.48 | ms wall |
| B/parallel | parallel status readers (40 processes) | 1507.23 | ms wall |
| C/sizes | sweep per slot | 13.2039 | ms/slot |
| C/sizes | snapshot archive bytes (1 MB source) | 1049212 (1.0 MB) | bytes |
| C/sizes | snapshot archive bytes (10 MB source) | 10489294 (10.0 MB) | bytes |
| C/sizes | snapshot archive bytes (50 MB source) | 52445127 (50.0 MB) | bytes |
| E/concurrency | HTTP concurrent throughput (8 clients) | 1691.3 | calls/s |
| F/soak | first-decile median | 6.512 | ms |
| F/soak | last-decile median | 49.796 | ms |
| F/soak | drift (last vs first) | 664.68 | % |
| F/soak | RSS before (VmRSS) | 71.95 | MB |
| F/soak | RSS after (VmRSS) | 71.96 | MB |
| F/soak | RSS delta (VmRSS) | 0.01 | MB |
| F/soak | registry slots at end | 300 | slots |

## Invariants

| Check | Result | Detail |
|---|---|---|
| 6-receipt bundle verifies TRUSTED | PASS | TRUSTED |
| 100-receipt bundle verifies TRUSTED | PASS | TRUSTED |
| tampered 100-receipt bundle is UNTRUSTED | PASS | bad_signature,chain_break |
| no lost updates at 4 parallel writers | PASS | failures=0 slots=20/20 |
| no lost updates at 8 parallel writers | PASS | failures=0 slots=60/60 |
| no lost updates at 16 parallel writers | PASS | failures=0 slots=140/140 |
| parallel readers all succeed | PASS | failures=0 |
| bench flow bundle verifies TRUSTED | PASS | TRUSTED |
| sweep sealed the fresh batches | PASS | sealed=[500, 500, 500] |
| list_ returns all seeded slots | PASS | count=10000 |
| operator kills stopped the run | PASS | n=10 |
| egress deny invariants hold | PASS | all runs non-zero exit |
| concurrent HTTP clients all succeed | PASS | errors=0 |
| soak final bundle verifies TRUSTED | PASS | TRUSTED |

- 1,000 full tasks ≈ 5.3 MB of receipt bundles
- 100,000 full tasks ≈ 527.1 MB of receipt bundles
- 1,000,000 full tasks ≈ 5.1 GB of receipt bundles

- Minimal task (pass+termination) is 30.4% of a full task bundle

## Observations

- Bundle verification scales near-linearly: 100 receipts take 17.6x the 6-receipt time (22.2414 ms vs 1.2611 ms).
- Registry reads grow with state file size: get_slot is 116.2x slower at 10k slots (43.2313 ms vs 0.3719 ms) — each read reparses the JSON registry.
- Containment overhead: raw bwrap 27.7603 ms, through the gate 34.5752 ms, slice-isolated 96.706 ms per exec.
- HTTP connection reuse matters: keep-alive ping 0.4182 ms vs 0.858 ms per call with a fresh connection.
- Operator kill latency: median 50.9756 ms, p95 1109.8601 ms (n=10).
- Soak: 300 flows, median 28.0188 ms, drift 664.68% between first and last decile; the drift tracks registry growth (300 slots at end, RSS delta 0.01 MB), not a process leak — see B for the registry-size curve.

