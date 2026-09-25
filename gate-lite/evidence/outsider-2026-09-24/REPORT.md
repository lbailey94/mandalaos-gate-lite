# gate-lite outsider exercise — 2026-09-24

**Candidate pin (tested code):** `mandala-os` commit
`ac078e2087be995720041ef100fce8c37be0ccd2` (local `main`, unpushed at run time),
exported with `git archive` (tracked files only — no untracked evidence, no
local state). Later commits `e7d40f5` (protocol + pointers) and `a4553b0`
(docs fixes below) are **documentation/evidence only** — no gate-lite code
changed after the pin.
**Result:** **PASS** — 86/86 tests, real-runner exec, 6-receipt bundle TRUSTED,
offline verification TRUSTED (exit 0).
**Run window:** 2026-09-24 00:51:37Z → 00:52:57Z (~80 s), host: test machine.

Protocol: `GATE_LITE_OUTSIDER_EXERCISE.md`.
Sovereign stranger-install and VM re-verification are **separate gates** and
were not touched by this run.

## Environment (recorded at run time)

| Item | Value |
|---|---|
| Host / OS | test machine · Zorin OS 18.1 · kernel 7.0.0-31-generic |
| Python | 3.12.3 (venv; host is PEP 668 managed) |
| gate-lite | 0.0.1 editable from the pinned export |
| continuity-receipt | 0.3.3 (PyPI) |
| cryptography | 50.0.1 (cffi 2.1.1, pycparser 3.0) |
| Runner | `~/.local/bin/mandala-sandbox` sha256 `de273c62ae22147634164e84cc9b6f6ae83a7f25e05755b50bc7c1257f525641` (source: `MANDALAOS_SOVEREIGN/modules/landlock-isolation.nix`) |
| bubblewrap | 0.9.0 |
| jq | 1.7 |

## Exact steps (as run; copy-paste order)

```bash
# 0. workspace + pinned export
mkdir -p <workspace>/src
cd ~/Desktop/MANDALA_OS
git archive ac078e2087be995720041ef100fce8c37be0ccd2 | tar -x -C <workspace>/src

# 1. install (venv required on PEP 668 hosts)
cd <workspace>
python3 -m venv venv
venv/bin/pip install -e src/gate-lite

# 2. documented quick start (README), from src/gate-lite
cd src/gate-lite
../../venv/bin/python tools/make_vectors.py
../../venv/bin/python -m unittest discover -s tests -v

# 3. governed flow with the real sandbox runner
export WM_GATELITE_RUNNER="$HOME/.local/bin/mandala-sandbox"
PY=../../venv/bin/python
$PY gate_lite/ctl.py --state ./state tenant-add --tenant dogfood --agent did:key:zOutsiderAgent1
PASS=$($PY gate_lite/ctl.py --state ./state pass --tenant dogfood --agent did:key:zOutsiderAgent1 --minutes 30 --spend-minor 1000)
SLOT=$(echo "$PASS" | jq -r .slot_id); TOKEN=$(echo "$PASS" | jq -r .token)
$PY gate_lite/ctl.py --state ./state exec --tenant dogfood --slot "$SLOT" \
    --payload-ref "echo hello from outsider" --token "$TOKEN"
$PY gate_lite/ctl.py --state ./state settle --tenant dogfood --slot "$SLOT" \
    --rail invoice --rail-ref outsider-0001 --minor 0
TASK=$($PY gate_lite/ctl.py --state ./state terminate --tenant dogfood --slot "$SLOT" | jq -r .task_id)
$PY gate_lite/ctl.py --state ./state receipt --task-id "$TASK" --verdict

# 4. offline verification (independent of the gate)
../../venv/bin/continuity-receipt-verify "state/receipts/$TASK.json"
$PY -m continuity_receipt.verify vectors/02_happy_full.json
```

## Results

**Classification correction (2026-09-25):** The `bwrap-landlock` value below
is the historical signed issuer claim. The portable wrapper at the recorded
digest invokes Bubblewrap, with no Landlock invocation observed in its source.
The exercise distinguished a real runner from the stub, but did not prove that
both confinement mechanisms were applied. Its same-host result does not close
runner classification or independent other-host adoption. Original bundle
and verifier artifacts are unchanged.

- `make_vectors.py`: 11 vectors written.
- Tests: `Ran 86 tests ... OK` (18.9 s) — independently reproduces the
  reported 86/86 on the pinned export with PyPI `continuity-receipt 0.3.3`.
- Exec (real runner): `exit 0`, `stdout_hash
  sha256:70f56b165788f44bafc9484bd779004ab3d8c5d1cea0e9417f7c7a61ee7dcbcc`;
  `task.execution.sandbox_class = "bwrap-landlock"` (proves the real runner,
  not the stub).
- Settlement: $0.00, `rail_ref outsider-0001`.
- Bundle: 6 receipts — `session.pass.created`, `task.decision`,
  `task.execution`, `delivery.attestation`, `settlement`, `task.termination`.
- `mandala-ctl receipt --verdict`: `TRUSTED`, `errors: []`.
- Offline verification: `continuity-receipt-verify bundle-task-*.json` →
  `TRUSTED` (exit 0); `python -m continuity_receipt.verify` → `TRUSTED`
  (exit 0, emits a runpy RuntimeWarning, see friction 4); standalone vector
  `vectors/02_happy_full.json` → `TRUSTED` (exit 0).

## Friction log (every point a tester needs help)

1. **No install step in the README.** The quick start assumes the package and
   its dependency are installed. On a PEP 668 host, `python3 -m unittest`
   fails with `ModuleNotFoundError: No module named 'continuity_receipt'`
   until a venv + `pip install -e .` is created. The README should show these
   two commands.
2. **Runner provenance is outside this slice.** `mandala-sandbox` lives in
   `MANDALAOS_SOVEREIGN/modules/landlock-isolation.nix`; gate-lite's README
   references `~/.local/bin/mandala-sandbox` but not where to get it or how
   to install it. Without it, exec correctly refuses (stub guard) — a
   stranger is blocked here until the wrapper is provided.
3. **Token extraction is undocumented.** The quick start shows
   `--token <token>` but not that the token must be parsed from the `pass`
   JSON output (needed `jq -r .token`). One line in the README would fix it.
4. **`python -m continuity_receipt.verify` emits a runpy warning**
   (`found in sys.modules after import of package ...`). Cosmetic; the
   console script `continuity-receipt-verify` is clean. Docs could prefer the
   console script (continuity-receipt repo, peer lane).
5. **`tools/make_vectors.py` rewrites tracked vector files** (fresh UUIDs /
   timestamps), dirtying `git status` in a clone. Correct for a throwaway
   export, surprising in a working tree; the README doesn't warn.
6. **The private export lacks the review scaffolding** (`LICENSE`, `SECURITY.md`,
   `CONTRIBUTING.md`, CI) — those exist only in the curated public snapshot.
   A stranger given the private tree has no license/security entry point.
7. **Slice mode (systemd cgroup quotas) was not exercised** — this run is
   real-runner only by design; slice mode remains covered by the 09-18
   dogfood evidence and the G2 tests.
8. **Minor:** the `settle` response has no top-level `slot_id` (the README
   examples don't depend on it, but tooling might).

**Friction status (2026-09-24, after review #209):** items 1–5 are addressed
by docs commit `a4553b0` (verified literally: the documented quick-start block
re-run against the pinned export → exec exit 0, bundle TRUSTED, console verify
TRUSTED); item 6 is a snapshot-curation concern; items 7–8 are noted and
unchanged.

## Claim boundary

This was a **clean-export reproduction on the same host, using a pre-existing
runner, performed by a collaborator**. It establishes: the pinned tree
installs, its tests pass, the real-runner path executes, and the emitted
bundle verifies offline with the published 0.3 verifier. It does **not**
establish an unassisted install by a new tester on a different machine — that
remains a separate gate if that claim is needed. The public snapshot must
carry this label.

## Files in this directory

- `transcript.txt` — full command/output log of the run.
- `exec.json`, `verdict.json` — exec and `receipt --verdict` outputs.
- `bundle-task-01a0d0e6-457e-7d76-8599-b6e70339d7a8.json` — the task bundle;
  verifies offline with `continuity-receipt 0.3.3`.
