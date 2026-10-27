# Wire Protocol 7369 profile proposal

**Profile URN:** `urn:mandala:runner-profile:gap-mesh-7369`  
**Status:** declarative only; execution unavailable.

The number 7369 is a project designation, not IETF RFC 7369, which specifies
an unrelated Ethernet OAM protocol.

This directory records a proposed mesh policy. It is not a runner and the
current Gate-Lite dispatcher does not select or execute it. Gate-Lite has no
TCP port/destination mediation or Ed25519 peer-authentication adapter for this
profile. The 64-byte Ed25519 signatures, port-only egress, DNS/cloud blocking,
and latency statements describe design intent only. Setting environment
variables or presenting this JSON does not enforce those controls.

The executable runner selector recognizes only the locally reviewed
`bwrap-v1` identity. Any other executable, including a future mesh adapter,
remains `unknown` and is refused before payload spawn until a separately
reviewed executable identity and mechanism evidence are wired into the
dispatcher. The policy fields below are not proof or runtime configuration.

The machine-readable proposal is in
[`runner-profile-gap-mesh.json`](runner-profile-gap-mesh.json).
