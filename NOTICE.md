# Licensing notice

- **Repository code** — the `gate-lite/` orchestrator, CLI, MCP server, tests,
  tools, and the root-level documents unless noted otherwise — is provided
  under the **MIT License** (`LICENSE`, © 2026 Lucas Bailey).
- **`continuity-receipt`** — the receipt library and reference verifier — is a
  separate work, licensed **Apache-2.0**. It is **not vendored** in this
  snapshot: it is installed from PyPI (`continuity-receipt==0.5.0`) and
  published at github.com/lbailey94/continuity-receipt. A copy of its license
  text is kept at the snapshot root as `LICENSE-APACHE-2.0`.
- **Documentation** (`*.md` design notes, briefings, status documents,
  evidence summaries) is provided under MIT unless a document states
  otherwise.
- The continuity-receipt format is published separately at
  github.com/lbailey94/continuity-receipt under Apache-2.0.

- **Public wrapper packet** — `gate-lite/runners/bwrap-v1/` retains its adjacent MIT license, provenance and source attribution. Distribution of that packet does not relicense either private upstream repository. The argv tests in `gate-lite/tools/test_sandbox_argv.py` adapt the Bubblewrap subset of Sovereign `9a0faf19fbebfd6a4c803822ed23e8ba6cf055b6:tests/test_sandbox_argv.py` (path adaptation, Landrun cases excluded, partial-output jq shim repaired); repository MIT applies to this distributed test adaptation.
