# Wire Protocol 7369 Sovereign Mesh Runner Profile

**Profile URN:** `urn:mandala:runner-profile:gap-mesh-7369`  
**Substrate Version:** Mandala Gate-Lite 0.5  
**Governing Design:** Gate-Lite Sovereign Containment · WhiteMagic Wire Protocol port 7369
(the "7369" is a project designation — NOT IETF RFC 7369, which specifies an unrelated Ethernet OAM protocol)  

---

> **STATUS (2026-10-15): proposal / declaration only — NOT yet enforced.** The Gate-Lite runtime
> implements the `bwrap-v1` profile; the guarantees described here (port-only egress, blocked
> DNS/cloud, socket-boundary peer refusal, sub-millisecond streaming) are the intended design of
> this profile, not present behavior. The included tests validate JSON field values, not runtime
> enforcement. Do not rely on these properties for containment until an executable mechanism and
> negative tests land.

## 1. Objective & Security Model (intended design — see status note)

The `gap-mesh-7369` runner profile extends Mandala Gate-Lite's capability isolation to permit **sub-millisecond peer-to-peer Gap-Junction codon streaming** while maintaining absolute zero-cloud egress protection:

1. **Port Restriction:** Only TCP port `7369` connections are permitted.
2. **Mutual Cryptographic Identity:** Every packet must be authenticated via 64-byte Ed25519 (dalek) signatures (`Zero-Bypass Remote Ingress`).
3. **No General Internet Egress:** Standard outbound ports (HTTP `80`, HTTPS `443`, SSH `22`, etc.) remain completely blocked.
4. **No DNS Resolution:** DNS resolution files (`/etc/resolv.conf`, `/run/systemd/resolve`) are withheld, preventing DNS tunneling or external resolution leakage.
5. **Fail-Closed Guarantee:** Unallowlisted peer IP targets or unrecognized keys are immediately dropped at the socket boundary without granting local execution capability.

---

## 2. Specification

The formal schema definition is located at [`runner-profile-gap-mesh.json`](runner-profile-gap-mesh.json).
