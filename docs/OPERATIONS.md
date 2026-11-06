# Operations and security

## Service boundary

| Role | Allowed | Not provided |
|---|---|---|
| Freqtrade | Request an entry grant; manage simulated positions | Operator/research token |
| Risk service | Read engine state; validate proposals; write ledger | Exchange credentials; order-submission code |
| Research | Publish a typed, expiring research report | Engine/admin token; Docker socket; deployment volume |
| OpenClaw | Read status, research and decisions | Mutations, approvals, exchange/API administrator credentials |
| Human operator | Halt/resume entries; inspect dashboard | Automatic strategy promotion |

The control service holds a Freqtrade API credential to read state. That credential is technically capable of other Freqtrade API actions: the collector only uses GET, but this is not a broker-enforced read-only credential. The service is therefore a trusted component, not an untrusted-agent sandbox. Force entries and position adjustment are disabled in the reviewed engine configuration.

A privileged operator, compromised engine, Docker administrator or shared unrestricted Unix account can bypass application controls. Restrict filesystem ownership, run OpenClaw as a separate unprivileged user, remove its access to Docker and sudo, and do not mount secrets or source code into the agent environment. Containers alone do not protect against host root. This release contains no exchange keys and cannot knowingly run live.

## Entry lifecycle

1. Freqtrade calculates a causal baseline signal and sizes a proposed limit entry.
2. Its confirmation callback sends a new random request ID, pair, amount and rate to the gate.
3. A PostgreSQL row lock serializes policy checks and cash/exposure reservations. Replayed request IDs never receive another grant.
4. The gate requires a fresh authenticated engine snapshot and independent public quote observation, then checks spread, price deviation, exposure, cash, daily entries and planned risk.
5. An optional AI filter may deny a baseline entry, but cannot bypass any check.
6. Freqtrade may submit a **simulated** order only after an explicit matching `allowed: true` response. Timeout, malformed JSON, missing token and database errors deny the entry without a retry.
7. The collector replaces reservations with observed open/pending exposure. Unused reservations expire only after a later successful reconciliation. Entry grants, rather than fills, consume the daily counter conservatively.

Reconciliation runs every 10 seconds. A failed collection invalidates approvals immediately after that failure is observed; timestamps also expire. Polling cannot remove the race between a market change and the next observation. Kraken ticker responses do not supply an exchange event timestamp in this adapter; `observed_at` is local observation time, not proof of upstream freshness. Use timestamped venue data and tighter lifecycle reconciliation before live trading.

The ledger keeps the UTC-day starting equity and a persistent high-water mark. Breakers include unrealized effects through the engine's simulated equity. They latch until an operator can legitimately resume; restarting services does not reset them. The drawdown baseline is not reset via an API. Future capital flows or baseline changes need an audited migration.

## Restarts and backups

Docker restart policies bring services back after daemon restart. Enable your Docker service at boot using your Ubuntu administration process. Stop/start the same Compose project to retain `ledger`, `engine`, `research-cache` and `reports` volumes. Do not use `down -v` except for disposable CI/testing: it deletes the audit state and simulated portfolio.

For a consistent paper backup, halt entries, inspect pending orders, stop the engine, dump PostgreSQL, and archive the engine volume using your backup process. Test restoration in a separate Compose project. Backing up only one of the two databases can leave control reservations inconsistent with engine state. Never restore a simulated wallet as if it were an exchange account.

## Troubleshooting

- `ready: false`: inspect `reconcile_error`, `halt`, observation timestamps, engine logs and current settings. Do not widen TTLs to hide an outage.
- `401`: check role-specific credentials. The read token cannot authorize or halt; the admin token cannot request entry grants.
- Repeated entries denied: inspect `/v1/decisions` and risk sizing. A pending reservation can conservatively block a replacement until reconciliation.
- No strategy signals: a running strategy does not promise frequent entries. Startup history and crossover conditions must be satisfied.
- Research `REVIEW`: provider/model mismatch, data failure, timeout or unparseable upstream rating. It never becomes a fabricated Buy.
- API provider outage: baseline continues in shadow mode. Filter mode denies new entries once the report expires. Existing exits remain engine-managed.

Do not expose ports 8080, 8081 or PostgreSQL publicly. Access the dashboard through SSH or a private VPN. Keep hosts time-synchronized. Check Docker disk use, logs and database growth. Keep secrets out of screenshots, issues, prompts and logs.
