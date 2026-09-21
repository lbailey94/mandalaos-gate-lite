# Security policy

## Scope

This repository is a **public-review snapshot** of MandalaOS gate-lite. Its
containment class is **shared-kernel** (bubblewrap/Landlock): it isolates
cooperating tenants from each other and from the host filesystem in a
single-user deployment. It is **not** an untrusted multi-tenant security
boundary — that is gate-hard (microVM floor), which is not built. Reports
that assume gate-lite is a tenant isolation boundary will be answered with
that distinction.

## Reporting a vulnerability

Please report suspected vulnerabilities privately:

1. GitHub Security Advisory (preferred) — repository → **Security** →
   **Report a vulnerability**.
2. Email <lbailey94@protonmail.com>.

Do not open a public issue for a vulnerability. Include `file:line`
references, a reproducer if possible, and the affected commit. The review map
in [`REVIEW_NOTES.md`](REVIEW_NOTES.md) lists the attacks the maintainer most
wants examined — findings there are welcome.

## What to expect

- Acknowledgment within 48 hours.
- An assessment (accepted / needs more information / not a vulnerability,
  with reasoning) within 7 days.
- Honest failure reports are wanted, not polish. Accepted findings and their
  disposition are recorded in the repository's status notes.

## Out of scope

- The receipt format itself — report spec-level issues at
  [continuity-receipt](https://github.com/lbailey94/continuity-receipt)
  (see its `SECURITY.md`).
- Deployments that ignore the stated threat model (for example: running
  untrusted code without the runner, or exposing the MCP HTTP surface beyond
  loopback without a token).
