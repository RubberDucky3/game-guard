# Security and privacy

Game Guard does not accept remote commands or expose a network server. Treat local configuration and the optional Hermes CLI as trusted inputs/dependencies. No process is killed, suspended or reprioritized.

Keep `config.json`, `state/`, local job IDs, prompt contents and machine paths private. The sample configuration manages no schedules. Never add credentials to this repository. Runtime ownership fingerprints are hashes rather than copied scheduler prompts; status output can still contain local job IDs and process names.

The scheduler operation and ownership-file write are not transactional. A crash can conservatively leave a schedule paused, and polling/dispatch checks are not a global atomic execution barrier. See README safety limitations before relying on this for unattended work.

Report a security issue privately using GitHub's security-reporting interface if available; otherwise open an issue describing the class of problem without credentials, sensitive files or exploit payloads. This project has no guaranteed incident-response SLA.
