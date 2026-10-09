# bwrap-v1 runner — pinned `mandala-sandbox` wrapper

This directory publishes the reviewed Bubblewrap wrapper used by gate-lite's
qualified `bwrap-v1` runner profile, byte-for-byte, under a packet-scoped MIT
license.

| Item | Value |
|---|---|
| Executable | `mandala-sandbox` (mode 755) |
| Executable SHA-256 | `f7da8d6c3809ac5adbc4631c82fb9327abdb69638715bb0ea1493dc79996411e` |
| Source | private `lbailey94/mandalaos-sovereign` @ `9a0faf19fbebfd6a4c803822ed23e8ba6cf055b6`, `scripts/mandala-sandbox` — see [`SOURCE-ATTRIBUTION.md`](SOURCE-ATTRIBUTION.md) |
| License | MIT, packet-scoped — see [`LICENSE`](LICENSE). The wider private Sovereign and Mandala repositories are not relicensed. |
| Provenance | [`PROVENANCE.json`](PROVENANCE.json) records the frozen public commit and pinned tool identities |

## Acquire and verify

Fetch the packet at the published tag (or the `frozen_public_commit` recorded in
`PROVENANCE.json`, which pins the executable bytes):

```sh
REF='bwrap-v1-packet'
BASE="https://raw.githubusercontent.com/lbailey94/mandalaos-gate-lite/$REF/gate-lite/runners/bwrap-v1"

mkdir -p mandala-bwrap-v1 && cd mandala-bwrap-v1
for f in LICENSE README.md SOURCE-ATTRIBUTION.md PROVENANCE.json SHA256SUMS mandala-sandbox; do
  curl -fsSL "$BASE/$f" -o "$f"
done
sha256sum -c SHA256SUMS          # all files must report OK
chmod 755 mandala-sandbox
sha256sum mandala-sandbox        # must print f7da8d6c…96411e
```

## Use

```sh
export WM_GATELITE_RUNNER="$PWD/mandala-sandbox"
```

## Runtime requirements and limits

The wrapper requires `bubblewrap` (`bwrap`), `jq`, and coreutils available on
`PATH`. The gate-lite candidate profile pins the exact reviewed executable
identities: wrapper SHA-256
`f7da8d6c3809ac5adbc4631c82fb9327abdb69638715bb0ea1493dc79996411e`, bwrap
SHA-256 `e318903862396f96de3df57264e0158682b952fd3fb53ac23d876413e7b30f71`,
and jq SHA-256
`59cfd58d7e470b103aede0e7589cfea929e45ee27f5471f08aa9676ac7bfc566`.
A different tool build or host requires fresh reviewed profile evidence; the
pinned hashes do not imply universal compatibility.

This uses shared-kernel Bubblewrap containment for cooperative workloads. It
is not Landlock, virtualization, or hostile-tenant isolation. The argv tests
use a capture shim and do not establish real containment. Network mode shares
the host network namespace and permits egress; the default mode requests a
private network namespace. Runtime behavior still depends on host kernel,
Bubblewrap support, filesystem layout, and the exact reviewed tools.
