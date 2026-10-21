# Plan — public Game Guard export

Goal: publish a reusable, privacy-safe Game Guard repository without altering the installed local automation.

1. Export only source and portable fixture tests, not runtime/business files.
2. Replace machine-specific adapter binding with an explicit Hermes-home setting; start with an empty managed-job allowlist.
3. Add validation, privacy-preserving ownership fingerprints, documentation, license and offline Windows/Linux CI.
4. Run local tests and CLI smoke checks, independently review staged changes, inspect publication contents, then create the public repository and verify remote state.

Layout: gaming_guard.py, test_gaming_guard.py, config.example.json, examples/, .github/workflows/, README.md, LICENSE.

Risks/stop conditions: do not publish private configuration/state/logs or credentials; stop if privacy checks fail, GitHub auth targets the wrong account, the chosen repository already exists, or review finds unresolved security/logic problems. No alteration to the deployed guard or global config. No paid API or model call in the guard/CI.
