# Gate-lite benchmark report

- Profile: **standard** · recorded 2026-09-18T17:16:52Z
- Host: Intel(R) Core(TM) i5-8350U CPU @ 1.70GHz · 8 threads · 15867 MB RAM · kernel 7.0.0-31-generic
- Python 3.12.3 · bubblewrap 0.9.0 · systemd 255 (255.4-1ubuntu8.17)
- Runner: `~/.local/bin/mandala-sandbox` · load avg at start [16.87890625, 12.9619140625, 8.2392578125]

Method: warmup, auto-calibrated n against a per-case time budget; latency
percentiles are over per-operation samples. Percentiles on low-n latency
cases (snapshot, kill, OOM) are indicative, not distribution-grade.

## A

| Case | n | median | p95 | p99 | mean | sd | min | max | per sec |
|---|---|---|---|---|---|---|---|---|---|
| canonicalize body (small, ~0.3 KB) | 2000 | 0.0166 ms | 0.0343 ms | 0.0523 ms | 0.0195 ms | 0.0138 ms | 0.016 ms | 0.3276 ms | 51359.47 |
| canonicalize body (large, ~20 KB) | 641 | 1.6663 ms | 2.4006 ms | 2.8821 ms | 1.6664 ms | 0.4686 ms | 1.0334 ms | 3.98 ms | 600.09 |
| commit_field (small body) | 2000 | 0.0357 ms | 0.0471 ms | 0.0553 ms | 0.0317 ms | 0.0105 ms | 0.0185 ms | 0.0806 ms | 31587.53 |
| sign_receipt (Ed25519) | 2000 | 0.1099 ms | 0.1943 ms | 0.2342 ms | 0.1293 ms | 0.0413 ms | 0.0886 ms | 0.6715 ms | 7735.98 |
| verify bundle (6 receipts) | 252 | 1.8188 ms | 2.8788 ms | 3.2806 ms | 1.9474 ms | 0.3737 ms | 1.5832 ms | 3.2977 ms | 513.51 |
| verify bundle (100 receipts) | 18 | 45.7335 ms | 62.4861 ms | 62.4861 ms | 42.4962 ms | 13.1233 ms | 26.004 ms | 62.4861 ms | 23.53 |
| build chain (100 receipts) | 41 | 25.0667 ms | 35.8231 ms | 40.3561 ms | 25.5388 ms | 6.514 ms | 16.6034 ms | 40.3561 ms | 39.16 |
| verify tampered bundle (100 receipts) | 14 | 38.5745 ms | 52.5903 ms | 52.5903 ms | 38.4423 ms | 7.2591 ms | 28.7304 ms | 52.5903 ms | 26.01 |

## B

| Case | n | median | p95 | p99 | mean | sd | min | max | per sec |
|---|---|---|---|---|---|---|---|---|---|
| get_slot (100 slots) | 2000 | 0.019 ms | 0.0335 ms | 0.0422 ms | 0.0206 ms | 0.0053 ms | 0.018 ms | 0.1023 ms | 48541.78 |
| put_slot (100 slots) | 2000 | 0.0742 ms | 0.1169 ms | 0.1388 ms | 0.0979 ms | 0.3613 ms | 0.0692 ms | 11.3519 ms | 10210.03 |
| recall miss (100 slots) | 2000 | 0.0086 ms | 0.0147 ms | 0.02 ms | 0.0095 ms | 0.0027 ms | 0.0082 ms | 0.0434 ms | 105241.37 |
| get_slot (1000 slots) | 2000 | 0.0202 ms | 0.038 ms | 0.0493 ms | 0.0235 ms | 0.0071 ms | 0.0189 ms | 0.0631 ms | 42492.37 |
| put_slot (1000 slots) | 2000 | 0.13 ms | 0.1608 ms | 0.188 ms | 0.1754 ms | 1.6794 ms | 0.0783 ms | 74.2148 ms | 5701.83 |
| recall miss (1000 slots) | 2000 | 0.0098 ms | 0.0202 ms | 0.0271 ms | 0.012 ms | 0.0045 ms | 0.0086 ms | 0.0564 ms | 83281.71 |
| get_slot (10000 slots) | 2000 | 0.0256 ms | 0.0506 ms | 0.0579 ms | 0.0307 ms | 0.01 ms | 0.0209 ms | 0.0801 ms | 32573.53 |
| put_slot (10000 slots) | 10 | 0.1275 ms | 0.1903 ms | 0.1903 ms | 0.1376 ms | 0.0235 ms | 0.1188 ms | 0.1903 ms | 7269.73 |
| recall miss (10000 slots) | 2000 | 0.0147 ms | 0.022 ms | 0.034 ms | 0.0172 ms | 0.0923 ms | 0.0085 ms | 3.8549 ms | 58018.76 |

## C

| Case | n | median | p95 | p99 | mean | sd | min | max | per sec |
|---|---|---|---|---|---|---|---|---|---|
| full flow (pass/exec/settle/terminate) | 104 | 5.3886 ms | 8.5146 ms | 48.6556 ms | 7.2833 ms | 11.5673 ms | 4.4324 ms | 112.8099 ms | 137.3 |
| flow without settlement (3 receipts) | 196 | 3.8523 ms | 7.5628 ms | 49.6842 ms | 5.4456 ms | 7.4633 ms | 3.1707 ms | 55.1782 ms | 183.64 |
| idempotent replay (pass+exec) | 2000 | 0.0732 ms | 0.1192 ms | 0.1772 ms | 0.0806 ms | 0.0234 ms | 0.0678 ms | 0.653 ms | 12404.92 |
| sweep 500 expired slots (fresh batch) | 3 | 445.193 ms | 517.7616 ms | 517.7616 ms | 444.7306 ms | 73.2633 ms | 371.2372 ms | 517.7616 ms | 2.25 |
| snapshot workspace 1 MB | 5 | 46.4002 ms | 47.5529 ms | 47.5529 ms | 46.582 ms | 0.954 ms | 45.1879 ms | 47.5529 ms | 21.47 |
| restore workspace 1 MB | 5 | 13.0708 ms | 13.2586 ms | 13.2586 ms | 12.9426 ms | 0.3439 ms | 12.3598 ms | 13.2586 ms | 77.26 |
| snapshot workspace 10 MB | 5 | 528.1885 ms | 554.7784 ms | 554.7784 ms | 516.3224 ms | 34.9573 ms | 471.2978 ms | 554.7784 ms | 1.94 |
| restore workspace 10 MB | 5 | 126.9115 ms | 131.596 ms | 131.596 ms | 122.8792 ms | 8.9874 ms | 109.511 ms | 131.596 ms | 8.14 |
| snapshot workspace 50 MB | 3 | 2386.749 ms | 2466.7395 ms | 2466.7395 ms | 2397.7272 ms | 64.2307 ms | 2339.6931 ms | 2466.7395 ms | 0.42 |
| restore workspace 50 MB | 3 | 539.5909 ms | 661.0085 ms | 661.0085 ms | 574.8488 ms | 75.0253 ms | 523.9471 ms | 661.0085 ms | 1.74 |
| list_ tenant slots (10k registry) | 6 | 96.5296 ms | 111.0184 ms | 111.0184 ms | 96.068 ms | 10.8639 ms | 82.1458 ms | 111.0184 ms | 10.41 |

## D

| Case | n | median | p95 | p99 | mean | sd | min | max | per sec |
|---|---|---|---|---|---|---|---|---|---|
| raw wrapper exec (bwrap, echo) | 25 | 33.8819 ms | 35.865 ms | 36.2403 ms | 33.5738 ms | 1.664 ms | 29.9958 ms | 36.2403 ms | 29.79 |
| gate exec via SandboxRunner (echo) | 22 | 35.1462 ms | 37.458 ms | 39.0051 ms | 35.3589 ms | 1.3413 ms | 32.7382 ms | 39.0051 ms | 28.28 |
| gate exec via SliceRunner (echo) | 10 | 97.3681 ms | 104.4083 ms | 104.4083 ms | 97.8459 ms | 3.5233 ms | 92.1832 ms | 104.4083 ms | 10.22 |
| operator kill latency (sleep payload) | 10 | 50.8482 ms | 51.327 ms | 51.327 ms | 50.8917 ms | 0.1673 ms | 50.7556 ms | 51.327 ms | 19.65 |
| egress-denied curl exec | 18 | 43.3781 ms | 81.6194 ms | 81.6194 ms | 48.8289 ms | 11.3368 ms | 41.1454 ms | 81.6194 ms | 20.48 |

## E

| Case | n | median | p95 | p99 | mean | sd | min | max | per sec |
|---|---|---|---|---|---|---|---|---|---|
| HTTP keep-alive ping | 968 | 0.549 ms | 0.7416 ms | 0.8804 ms | 0.5721 ms | 0.1034 ms | 0.3997 ms | 1.7006 ms | 1747.9 |
| HTTP keep-alive status | 1439 | 0.6915 ms | 1.0933 ms | 1.7251 ms | 0.7544 ms | 0.3123 ms | 0.4712 ms | 7.1729 ms | 1325.49 |
| HTTP per-connection ping (urllib) | 631 | 1.1511 ms | 1.7037 ms | 3.2523 ms | 1.2319 ms | 0.4597 ms | 0.8097 ms | 6.8785 ms | 811.74 |
| HTTP concurrent ping (8 clients x 50) | 400 | 4.1513 ms | 8.025 ms | 10.4689 ms | 4.4383 ms | 1.9081 ms | 0.5431 ms | 11.8171 ms | 225.31 |
| stdio ping | 2000 | 0.0478 ms | 0.084 ms | 0.1067 ms | 0.0523 ms | 0.0172 ms | 0.0322 ms | 0.1404 ms | 19117.54 |
| stdio status | 2000 | 0.1727 ms | 0.2714 ms | 0.4021 ms | 0.1882 ms | 0.2551 ms | 0.0907 ms | 7.5728 ms | 5314.51 |
| full lifecycle over stdio | 10 | 7.6477 ms | 16.6104 ms | 16.6104 ms | 8.2917 ms | 2.9922 ms | 5.6111 ms | 16.6104 ms | 120.6 |
| full lifecycle over HTTP keep-alive | 10 | 9.0661 ms | 23.3329 ms | 23.3329 ms | 10.753 ms | 4.6566 ms | 7.5321 ms | 23.3329 ms | 93.0 |

## F

| Case | n | median | p95 | p99 | mean | sd | min | max | per sec |
|---|---|---|---|---|---|---|---|---|---|
| soak flow latency (300 flows) | 300 | 3.7426 ms | 6.794 ms | 139.0887 ms | 7.2725 ms | 26.6361 ms | 2.7971 ms | 368.1717 ms | 137.5 |

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
| B/sizes | registry db bytes (100 slots) | 152448 (148.9 KB) | bytes |
| B/sizes | registry db bytes (1000 slots) | 519128 (507.0 KB) | bytes |
| B/sizes | registry db bytes (10000 slots) | 4111768 (3.9 MB) | bytes |
| B/parallel | parallel pass writers (4 workers x 5) | 953.53 | ms wall |
| B/parallel | parallel pass writers (8 workers x 5) | 1730.59 | ms wall |
| B/parallel | parallel pass writers (16 workers x 5) | 3312.46 | ms wall |
| B/parallel | parallel status readers (40 processes) | 1600.96 | ms wall |
| C/sizes | sweep per slot | 0.8904 | ms/slot |
| C/sizes | snapshot archive bytes (1 MB source) | 1049207 (1.0 MB) | bytes |
| C/sizes | snapshot archive bytes (10 MB source) | 10489300 (10.0 MB) | bytes |
| C/sizes | snapshot archive bytes (50 MB source) | 52445130 (50.0 MB) | bytes |
| D | OOM quota-seal latency | skipped | status |
| E/concurrency | HTTP concurrent throughput (8 clients) | 1742.6 | calls/s |
| F/soak | first-decile median | 4.199 | ms |
| F/soak | last-decile median | 3.972 | ms |
| F/soak | drift (last vs first) | -5.42 | % |
| F/soak | RSS before (VmRSS) | 58.56 | MB |
| F/soak | RSS after (VmRSS) | 56.28 | MB |
| F/soak | RSS delta (VmRSS) | -2.28 | MB |
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

- Bundle verification scales near-linearly: 100 receipts take 25.1x the 6-receipt time (45.7335 ms vs 1.8188 ms).
- Registry reads are independent of store size: get_slot at 10k slots is 1.3x the 100-slot time (0.0256 ms vs 0.019 ms) — indexed SQLite lookups replaced full JSON reparsing.
- Containment overhead: raw bwrap 33.8819 ms, through the gate 35.1462 ms, slice-isolated 97.3681 ms per exec.
- HTTP connection reuse matters: keep-alive ping 0.549 ms vs 1.1511 ms per call with a fresh connection.
- Operator kill latency: median 50.8482 ms, p95 51.327 ms (n=10).
- Soak: 300 flows, median 3.7426 ms, drift -5.42% between first and last decile.

