# Gate-lite outsider exercise — protocol v1 (2026-09-24)

**Purpose.** Exercise the **gate-lite slice** end-to-end from a pinned
candidate the way an outside tester would, with a **real sandbox runner**, and
record every point where the tester needs help. Evidence from this exercise is
what a public snapshot is curated around.

**Gate separation (do not conflate).**
- This protocol covers **gate-lite only**.
- `STRANGER_INSTALL_PROTOCOL.md` is the **Sovereign VM installation gate**
  (≥4/5 unassisted testers) — a separate gate with its own evidence.
- **Sovereign VM re-verification** after a WhiteMagic pin bump is a separate
  pending gate.
- Slice/systemd mode, MCP transports, and hosted lanes are **out of scope**
  here (covered by dogfood/bench/acceptance evidence elsewhere).

## 1. Candidate pinning

1. Record the exact commit: `git -C MANDALA_OS rev-parse HEAD` (and note
   whether it is pushed).
2. Export tracked files only into a fresh directory:
   `git archive <sha> | tar -x -C <workspace>/src`.
   Untracked local state (evidence dirs, caches, `state/`) must not travel.

## 2. Environment record

Record at run time: host/OS/kernel, Python version, venv use, `pip freeze` for
the relevant packages (`continuity-receipt`, `cryptography`, `cffi`,
`pycparser`), the runner path **and sha256**, `bubblewrap` version, `jq`.

## 3. Steps (as documented in `gate-lite/README.md`)

```bash
mkdir -p <workspace>/src
git -C MANDALA_OS archive <sha> | tar -x -C <workspace>/src
cd <workspace>
python3 -m venv venv
venv/bin/pip install -e src/gate-lite
cd src/gate-lite
../../venv/bin/python tools/make_vectors.py
../../venv/bin/python -m unittest discover -s tests -v
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
../../venv/bin/continuity-receipt-verify "state/receipts/$TASK.json"
$PY -m continuity_receipt.verify vectors/02_happy_full.json
```

## 4. Acceptance criteria

1. Test suite green on the export; count recorded.
2. Exec via the real runner: `exit 0` and `task.execution.sandbox_class` is the
   runner class (e.g. `bwrap-landlock`) — **not** `stub`.
3. Bundle `TRUSTED` from `mandala-ctl receipt --verdict` **and** offline from
   the published verifier (console script and module), exit 0.
4. $0 settlement recorded in the bundle.
5. Friction log complete: every point where the tester needed help (missing
   install step, runner provenance, token handling, warnings, dirty tree,
   absent scaffolding) — plus anything out of scope, stated as such.

## 5. Evidence and review

- Write `gate-lite/evidence/outsider-<date>/`: `REPORT.md`, `transcript.txt`,
  exec/verdict outputs, and the task bundle.
- Post a board summary (pin, environment, verdicts, friction list).
- **Review before curation:** the public snapshot is only curated after the
  evidence has been reviewed; the snapshot pins the tested candidate and
  carries the relevant evidence.

## 6. Claim boundary and labeling

A run by a collaborator on the same host with a pre-existing runner is
**reproducibility evidence**, not an unassisted stranger install. Snapshot
and summary text must label it accordingly ("clean-export reproduction on
<host> by a collaborator, pre-existing runner") and must identify the tested
**code** pin separately from later **documentation** revisions. If an
unassisted new-tester / other-host claim is needed, that is a separate
exercise with its own evidence.

First run: 2026-09-24, candidate `ac078e2` — report in
`gate-lite/evidence/outsider-2026-09-24/REPORT.md` (PASS with 8 friction
notes; reviewed #209; friction docs fixed in `a4553b0`).
