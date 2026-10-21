# Log — public export

## Publication preparation
Goal: make the gaming guard available as a public, portable source repository.

Exported only implementation and portable fixture tests into a separate checkout. Kept live automation unchanged. Removed machine-specific profile bindings, introduced an explicit local Hermes-home configuration, and made an empty allowlist the safe example default. Added input validation and hashed pause ownership so runtime state does not reproduce scheduler prompts. Each new behavior was preceded by an observed failing test.

Added usage/safety documentation, an MIT license, and Windows/Linux offline CI. Public configuration contains example process names only, with no real scheduler IDs or home paths. Publication and exact-head CI verification are separate subsequent checks; do not infer either from this log entry.

## 2026-10-21T07:55:45-05:00 — independent review gate
Local baseline: ten tests passed, staged whitespace checks passed, and staged privacy/static scan found no private runtime IDs, machine paths, credential assignments or forbidden runtime files. Created and read-back-verified an empty public remote. No source commit was pushed.

Independent review blocked source publication on two targeting flaws: relative scheduler-home paths and pause ownership not bound to scheduler identity. Dispatched a separate fix context limited to these flaws and regression tests; review must be rerun before publication. Live installed automation remains outside this export's scope.

## 2026-10-21T09:01:29-05:00 — publication gate passed
A separate fix context added canonical absolute-home enforcement, home-bound pause ownership and regression coverage. Corrected the safe example to omit an unset optional home rather than providing an invalid empty path. Parent reran seventeen tests, staged whitespace checks and the staged privacy/static scan successfully. A fresh independent review approved all thirteen staged files without blocking security or logic findings. The remaining suggestion is additional tick-level coverage for human re-pauses and policy edits. Proceeding with source publication; hosted CI must be checked on the exact pushed commit.
