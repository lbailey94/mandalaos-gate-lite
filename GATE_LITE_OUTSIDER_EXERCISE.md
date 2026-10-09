# Gate-lite outsider exercise — protocol v2 (0.5 selective port)

Status: candidate protocol for exact-source review. A local run remains a local
rehearsal. Publication requires a pushed source SHA, independently reviewed public
tree, wrapper acquisition proof, evidence review and human publication sign-off.
The accepted private exercise at `8e84b25` is distinct from a new public-port run.
[V1 is preserved](GATE_LITE_OUTSIDER_EXERCISE_V1_2026-09-24.md) as it appeared at
public base `75ebbd6`, including the later acquisition note.

This covers gate-lite's exact 0.5 `bwrap-v1` profile. Public main's 0.4 hold,
Sovereign VM qualification, unassisted installation, independent adoption, MCP
transports, destination filtering, and hostile-tenant isolation are separate gates.

## Source export and environment

Record full source SHA, visibility, remote reachability, export method and tree
status. A pushed private SHA is retrievable only by authorized collaborators.
Public reproduction must use public code and wrapper, without private access.

```bash
REPO=/path/to/source-checkout
SOURCE_SHA=<full-reviewed-40-character-sha>
W=$(mktemp -d)
mkdir "$W/src"
git -C "$REPO" archive "$SOURCE_SHA" | tar -x -C "$W/src"
python3 -m venv "$W/venv"
"$W/venv/bin/pip" install "$W/src/gate-lite"
PY="$W/venv/bin/python"
cd "$W/src/gate-lite"
"$PY" -c 'import continuity_receipt; assert continuity_receipt.__version__ == "0.5.0"'
"$W/venv/bin/pip" check
```

Use exact `continuity-receipt==0.5.0`; later versions are outside this profile.
Record OS/kernel, Python, relevant package versions, and wrapper/bwrap/jq hashes.
Confirm both export bytes and installed runtime match the frozen source.

## Public wrapper acquisition

The complete packet exercised on October 9 is pinned to full public commit
`1357c147410e2471872cb0658d93199457461e65`. Tag `bwrap-v1-packet` is a convenience
ref. Commit `a843e61…` identifies first-landed executable bytes and lacks two
packet metadata files; it is not a complete-packet acquisition pin.

Download without credentials into a fresh directory and verify its manifest:

```bash
PACKET_SHA=1357c147410e2471872cb0658d93199457461e65
mkdir "$W/wrapper-packet"
BASE="https://raw.githubusercontent.com/lbailey94/mandalaos-gate-lite/$PACKET_SHA/gate-lite/runners/bwrap-v1"
for file in LICENSE README.md SOURCE-ATTRIBUTION.md PROVENANCE.json SHA256SUMS mandala-sandbox; do
  curl -q --fail --silent --show-error "$BASE/$file" -o "$W/wrapper-packet/$file" || exit 1
done
(cd "$W/wrapper-packet" && sha256sum -c SHA256SUMS) || exit 1
chmod 755 "$W/wrapper-packet/mandala-sandbox"
RUNNER="$W/wrapper-packet/mandala-sandbox"
sha256sum "$RUNNER" /usr/bin/bwrap /usr/bin/jq
bash -n "$RUNNER"
```

The executable digest is
`f7da8d6c3809ac5adbc4631c82fb9327abdb69638715bb0ea1493dc79996411e`.
Public metadata fixes at `75ebbd6` have their own valid manifest; they do not
change the frozen exercised packet. Packet MIT applies to the distributed
wrapper, not to the private repositories. See the current packet attribution.
Run anonymous acquisition in a clean environment without token/cookie/netrc or
credential-helper access, and retain HTTP statuses and hashes. An ordinary curl
command alone does not demonstrate that its inherited environment was anonymous.

```bash
"$PY" tools/test_sandbox_argv.py -v > "$W/wrapper-tests.log" 2>&1
"$PY" tools/qualify_bwrap_runner.py --wrapper "$RUNNER" \
  --expected-wrapper-sha256 sha256:f7da8d6c3809ac5adbc4631c82fb9327abdb69638715bb0ea1493dc79996411e \
  --expected-bwrap-sha256 sha256:e318903862396f96de3df57264e0158682b952fd3fb53ac23d876413e7b30f71 \
  > "$W/mechanism-probe.json"
```

The argv script uses the bundled byte-identical wrapper with a capture shim;
record its byte equality with the downloaded wrapper. The fixed mechanism probe
uses the downloaded wrapper and checks namespace/filesystem properties, without
qualifying every outbound route. Another bwrap/jq build needs reviewed profile
evidence; do not edit hashes to force a pass. Check all exit statuses.

## Tests and fixture generation

Committed `vectors/` are historical 0.4 compatibility fixtures. Leave them
unchanged. Optional new corpus generation requires an explicit version and a
separate output directory, with aligned bundle, receipt, delivery and index labels:

```bash
"$PY" tools/make_vectors.py --spec 0.5 --out "$W/vectors-05"
"$W/venv/bin/continuity-receipt-verify" "$W/vectors-05/02_happy_full.json"
env -u WM_GATELITE_RUNNER -u WM_GATELITE_SLICE -u GATE_LITE_REAL_RUNNER_TESTS \
  -u GATE_LITE_QUOTA_TESTS "$PY" -m unittest discover -s tests -v > "$W/unit-clean.log" 2>&1
WM_GATELITE_RUNNER="$RUNNER" WM_GATELITE_SLICE=1 \
  "$PY" -m unittest discover -s tests -v > "$W/unit-configured.log" 2>&1
GATE_LITE_REAL_RUNNER_TESTS=1 WM_GATELITE_RUNNER="$RUNNER" \
  "$PY" -m unittest discover -s tests -p test_acceptance.py -v > "$W/acceptance-bwrap.log" 2>&1
```

Ordinary absence/demo guard tests neutralize ambient runner configuration.
Acceptance requires explicit real-runner opt-in and exact profile qualification.
An invalid requested profile fails preflight. Wall/OOM drills additionally need
`GATE_LITE_QUOTA_TESTS=1` and a ready systemd user manager. Record discovered,
passed, failed and skipped counts and each skip reason. The accepted October 9
exercise did not run wall/OOM qualification. An echo flow alone is not kill,
egress, quota or snapshot/restore coverage.

## Token-safe lifecycle and commitment capture

```bash
"$PY" tools/capture_outsider_05.py --out "$W/outsider-05" \
  --runner "$RUNNER" --source-sha "$SOURCE_SHA" --source-status local-reviewed
"$W/venv/bin/continuity-receipt-verify" "$W/outsider-05/bundle-task.json" \
  > "$W/outsider-05/console-verdict.json"
"$PY" -m continuity_receipt.verify "$W/outsider-05/bundle-task.json" \
  > "$W/outsider-05/module-verdict.json" 2> "$W/outsider-05/module-stderr.txt"
```

Use `pushed-frozen` only after separate verification of the exact remote SHA and
export bytes. The capture flag itself is an operator assertion. The tool drives
separate CLI processes, retaining the exact snapshot supplied to the original
commitment method without changing its value. Token handling is in memory/stdin;
no runtime database or signing key is exported. Keyed issuance caches plaintext
tokens privately; this capture deliberately uses unkeyed issuance. Direct CLI
supports exclusive `--token`/`--token-stdin`. Disable shell tracing; never tee raw
pass output. Successful execution burns the JTI across restart.

Require payload exit zero, class bwrap, expected wrapper and canonical invocation
digests, recomputed commitment count/head, $0 settlement, issuer delivery response
matching execution stdout, termination, and TRUSTED bundle. Preserve original
signed bundles, snapshots and transcripts; editing a commitment input invalidates
recomputation. Reject a privacy failure instead of sanitizing signed evidence.

## Review and claims

Record exact-source/CI checks separately from runtime capture, and have another
reviewer recompute the bindings. Console/module/API share one Python verifier;
they are three verification commands, not three independent implementations.
Rust parity needs its own versioned execution evidence. Mechanism probes, fixture
compatibility, receipt conformance and hash recomputation are separate views.

Same-host collaborator reproduction does not establish independent adoption.
Shared-kernel bwrap is not a VM or hostile-tenant boundary. TRUSTED does not prove
issuer honesty or actual enforcement. Issuer response binding is not external
delivery attestation; $0 invoice settlement is not payment qualification. Network
grants remain whole-network intent, not a destination allowlist.

Keep October 8 run A labeled expected 0.4 refusal (installed `de273…` wrapper),
run B at `8ea8c7e` labeled local-reviewed/pre-push (`f7da…` wrapper), and October 9
private `8e84b25` labeled its distinct frozen-source exercise. The old second-laptop
packet is superseded for current pins, while independent-host qualification stays
open. Review [the errata](GATE_LITE_05_REVIEW_ERRATA_2026-10-08.md) before reusing
historical claims. Port review and publication require their own recorded decisions.
