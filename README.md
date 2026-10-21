# Game Guard

[![Tests](https://github.com/RubberDucky3/game-guard/actions/workflows/test.yml/badge.svg)](https://github.com/RubberDucky3/game-guard/actions/workflows/test.yml)

**Pause new automation while you game. Let existing work finish safely.**

A small Windows process detector and dispatch gate for background automation, with an optional [Hermes Agent](https://hermes-agent.nousresearch.com/docs/) cron adapter. Python standard library only. No model, API key, paid service, administrator privileges, or package installation required.

## What it does

- Matches exact game process names, case-insensitively; launchers do not count.
- Supports automatic detection and a manual gaming-mode switch.
- Holds only explicitly allowlisted Hermes schedules.
- Persists ownership of verified pauses, then restores only unchanged owned pauses after a clear-period cooldown.
- Limits schedule restoration per tick to avoid resuming everything at once.
- Exposes a read-only exit-code gate for your own worker launcher.
- Never kills, suspends, or changes the priority of a process.

```text
Recognized game / manual switch / detector failure
                      |
                  GAMING (hold)
                      |
               no recognized games
                      |
                 COOLDOWN (hold)
                      |
              observed clear period
                      |
                  READY (allow)
```

## Quick start — Windows / Python 3.11+

```powershell
git clone https://github.com/RubberDucky3/game-guard.git
Set-Location game-guard
Copy-Item config.example.json config.json
python gaming_guard.py status
```

**Safe default:** `managed_job_ids` is empty. You can try detection and manual mode without changing any scheduler. Edit `game_processes` in your local config to add actual game executable names, with or without `.exe`.

```powershell
# Engage manual mode and evaluate it immediately:
python gaming_guard.py on

# Return to automatic detection (an actual game still takes precedence):
python gaming_guard.py off

# Run one control-loop iteration:
python gaming_guard.py tick

# Inspect fresh detection and last saved control state:
python gaming_guard.py status
```

Run `tick` periodically for automatic schedule control and cooldown progression. This program does not install a service or an infinite polling loop. Manual `off` does not bypass an active game or the cooldown; run periodic ticks until clear. Without a running scheduler, the stored hold stays conservative.

## Gate a worker launch

```powershell
python gaming_guard.py check
if ($LASTEXITCODE -eq 0) {
    # Start your approved background task here.
    Write-Output 'Dispatch permitted'
}
```

Exit codes: **0** = allowed/success; **3** = dispatch held; **1** = configuration/runtime failure. Treat every nonzero check result as a hold. `status` is informational and does not return 3 for a hold.

`examples/guarded_dispatch.py` demonstrates the same check from Python without starting an actual worker.

## Optional: manage Hermes schedules

1. Verify the desired Hermes profile is running and list its jobs using the supported CLI or Hermes tools.
2. Set `hermes_home` to that profile's absolute home directory, the directory containing `cron/jobs.json`.
3. Add only approved job IDs to `managed_job_ids`. Leave reminders and critical work out.
4. Verify `status`, then run `tick`. Writes use the supported `hermes cron pause/resume` CLI with an explicitly scoped `HERMES_HOME`; the guard does not rewrite the job registry itself.
5. Schedule `python gaming_guard.py tick` about once a minute using your existing scheduler. In Hermes, use a **script-only/no-agent** job, an absolute script path, and local delivery. Do not include the guard's own job in its allowlist.

Run `python gaming_guard.py --help` for the CLI. `--root PATH` selects a different directory containing local config/state, not a different source checkout.

Hermes must be installed on PATH only when managing nonempty job IDs. The adapter expects a JSON registry object containing a `jobs` array and pause metadata (`id`, `enabled`, `state`, `paused_at`). A future Hermes schema change may require adapter updates.

## Safety and scope

- **Not universal game detection.** Unknown executables, streamed games, and Minecraft Java's generic `javaw` need additional rules or manual mode. The starter list is not proof every game is covered.
- **Not a gaming performance guarantee.** Existing workers, local models, downloads and system services keep running. Nothing is force-stopped.
- **Polling is not atomic.** A schedule can start between game launch and the next tick. Recheck at your actual dispatch boundary; a launcher already executing can still proceed.
- **Conservative restoration.** Jobs disabled before the guard remain disabled. A later human pause or policy edit invalidates automatic restoration. Removing an ID from the allowlist while held does not unpause it. Each owned pause is bound to the canonical absolute `hermes_home` (`~` is expanded; relative paths are rejected). A changed home or legacy ownership without a home blocks automatic control of that job, reports an ownership error, and preserves the ledger for diagnosis. Restore the original configured home to recover bound ownership; for legacy entries, verify the intended scheduler and restore jobs manually before retiring the old ledger entries. Never copy or invent a home binding to authorize restoration.
- **Overdue jobs follow scheduler semantics.** Restoring a schedule may cause catch-up work. The resume limit reduces, but cannot eliminate, concurrent work.
- **Ownership persistence is not transactional with the external scheduler.** A crash after a CLI pause but before the ledger is written can leave an unowned paused job. Diagnose and restore it manually.
- **Detection failure holds work.** Corrupt/missing config/state or scheduler errors are reported as nonzero exits; they are not an OS-wide fail-safe. A stopped or broken polling service cannot prevent every future dispatch.
- **No startup guarantee.** Reboot/login recovery, PC power settings, backups, and remote control are separate configuration tasks.

## Privacy

Your `config.json`, state, manual marker and logs are gitignored. Pause ownership stores a SHA-256 fingerprint rather than copying job prompt text into state. Do not commit your runtime configuration, private home path, job IDs, or unrelated business files. No telemetry or network service is added by Game Guard itself; the optional Hermes CLI remains its own trusted dependency.

## Tests

```powershell
python -m unittest discover -v
```

Core tests are offline and portable; GitHub Actions runs them on Windows and Linux. Native process detection is Windows-specific. Tests use isolated fixture jobs, never your actual schedule or live models. Actual end-to-end gaming behavior should be checked against the games and scheduler version you use.

## Disable safely

Close recognized games, clear manual mode, keep ticking through cooldown, and confirm `state/state.json` has an empty `owned` map. Then disable your polling schedule. If you stop polling while the guard owns paused jobs, they stay paused. Remove any dispatch-gate integration separately if you no longer want it.

MIT licensed. See [LICENSE](LICENSE).
