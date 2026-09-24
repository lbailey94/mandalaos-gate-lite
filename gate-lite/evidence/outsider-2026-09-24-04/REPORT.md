# Gate-lite 0.4 clean-export reproduction — 2026-09-24

**Disposition: PASS for the bounded same-host exercise.** This was run by
Codex on the maintainer's host with a pre-existing real runner. It is
not an unassisted stranger install, a new-machine test, or Sovereign VM
qualification. The tested code pin was private `mandala-os`
`033e5ceb78ba608955c9b8e7986d7958bc4e6792`, already at `origin/main`.
Later documentation/evidence edits in the working tree were not in the export.

## Reproduction

1. `git archive 033e5ce | tar -x -C <workspace>/src`
2. `python3 -m venv <workspace>/venv`
3. `venv/bin/pip install -e src/gate-lite`
4. From `src/gate-lite`, run `tools/make_vectors.py`, then
   `python -m unittest discover -s tests -q`.
5. Configure `WM_GATELITE_RUNNER=~/.local/bin/mandala-sandbox` and run the
   documented tenant-add → pass → exec (`echo hello from outsider`) → $0
   settle → terminate → receipt flow with the returned single-use token.
6. Verify the bundle with `continuity-receipt-verify` and the module entry
   point; verify `vectors/02_happy_full.json` with the console entry point.

The pass token was used only inside the temporary run script. It is absent
from this evidence bundle and report.

## Environment and results

| Check | Result |
|---|---|
| Host | Same host as the maintainer, Zorin OS 18, Linux 7.0.0-31-generic; Python 3.12.3 |
| Clean export | tracked files from `033e5ce`; venv installed `continuity-receipt==0.4.0`, `cryptography==50.0.1`, `cffi==2.1.1`, `pycparser==3.0` |
| Runner | `~/.local/bin/mandala-sandbox`, SHA-256 `de273c62ae22147634164e84cc9b6f6ae83a7f25e05755b50bc7c1257f525641`; bubblewrap 0.9.0; jq 1.7 |
| Tests | 86 run, OK, one optional OOM drill skipped; see `tests.log` |
| Real execution | exit 0; receipt `task.execution.sandbox_class=bwrap-landlock` |
| Settlement | 0 USD minor units; rail reference `outsider-04` |
| Bundle | six receipts, `continuity-receipt/0.4`, SHA-256 `114283e2ba318322c1f61e0fd500fda8f28bb447800e6b02c64b96795afcbf9c` |
| Verification | gate CLI `TRUSTED`; published console verifier `TRUSTED` exit 0 (`verdict.json`); module verifier `TRUSTED` exit 0; regenerated happy vector `TRUSTED` exit 0 |

## Friction and scope

- The module verifier prints a runpy warning; the documented console command
  returns the same verdict without the warning.
- `tests.log` includes `ResourceWarning` lines for unclosed subprocess file
  handles, although the suite passes. This deserves a focused cleanup before
  calling the test output warning-free.
- The runner is supplied by the separate Sovereign checkout and was already
  installed. An external tester needs runner acquisition and provenance steps.
- Slice/systemd mode, MCP transports, external anchors, and hostile-tenant
  isolation were outside this exercise. Earlier dogfood/acceptance evidence
  covers some of those paths at older candidate pins.

The older `outsider-2026-09-24/` report remains the 0.3 exercise. Neither
bundle should be relabeled to the other's spec or treated as a production
release gate.
