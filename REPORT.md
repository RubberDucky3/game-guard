# Report — public Game Guard export

## Shipped source
Reusable Python source, example-only configuration, offline fixture tests, Windows CLI smoke coverage, a guarded-dispatch example, MIT license, safety documentation and a Windows/Linux CI workflow. The export is separate from the installed automation.

## Not shipped
Universal game detection, active-worker suspension, startup installation, a tray UI and GPU/model unloading are out of scope. This is a local utility with source on GitHub, not a deployed web service.

## Assumptions
Use a public repository named game-guard and an MIT license. Manage no jobs by default. Require an absolute, explicitly configured local Hermes home and selected schedule IDs for the optional adapter.

## Numbers
Seventeen offline tests passed locally on Windows, including native CLI manual-mode smoke checks. Independent review approved the privacy-safe export after regression-tested fixes for relative scheduler targeting and cross-home pause ownership. Staged whitespace and static/privacy scans passed. The primary runtime path uses no LLM/API calls; development-session cost/tokens are unavailable. Hosted CI must be checked on the published commit, not inferred from this report. The README badge and Actions page show current Windows/Linux Python 3.11/3.13 results; the native Windows test is intentionally skipped on Linux.

## Risks
Exact-name coverage only, polling windows, external-scheduler schema drift and crash gaps around ownership persistence. Actual game launch and current-user scheduler integration are not exercised by the public fixture suite. Native process discovery is Windows-only; portable core tests run on Linux too.

## Next brief suggestion
Test the process names of real installed games, then consider opt-in startup installation and a simple tray control. Do not expand scope to arbitrary process termination.
