"""Pass tokens (compact JWS, Ed25519) for gate-lite v0."""
import json

from continuity_receipt import keys
from continuity_receipt.canon import canonical_bytes


def _segments(header: dict, payload: dict) -> tuple[str, str, bytes]:
    signing_input = (
        keys.b64u(canonical_bytes(header)) + "." + keys.b64u(canonical_bytes(payload))
    )
    return signing_input


def issue_pass(gate_did: str, gate_key, claims: dict) -> str:
    header = {"alg": "EdDSA", "typ": "JWT", "kid": gate_did}
    signing_input = _segments(header, claims)
    signature = keys.sign(gate_key, signing_input.encode("ascii"))
    return signing_input + "." + signature


def verify_pass(token: str, gate_did: str, jti_cache: set | None = None) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("malformed pass token")
    signing_input = parts[0] + "." + parts[1]
    if not keys.verify(gate_did, signing_input.encode("ascii"), parts[2]):
        raise ValueError("bad pass signature")
    header = json.loads(keys.b64u_decode(parts[0]))
    if header.get("kid") != gate_did:
        raise ValueError("pass issued by a different gate")
    claims = json.loads(keys.b64u_decode(parts[1]))
    if jti_cache is not None:
        jti = claims.get("jti")
        if jti in jti_cache:
            raise ValueError("pass token replay")
        jti_cache.add(jti)
    return claims
