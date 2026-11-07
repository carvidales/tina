# TINA

An autonomous **paper-trading** crypto bot for an Ubuntu server, with Freqtrade execution, an independent entry-risk service, PostgreSQL audit history, optional TradingAgents research, and a read-only OpenClaw bridge.

**Status: initial integration, not a live-money release.** No strategy profitability is claimed. The launcher, strategy callback, and reconciler refuse live mode. Do not supply exchange API keys. This repository is not a substitute for exchange testing or a security audit.

## What runs together

```text
Kraken public data -> Freqtrade 2026.10 / TinaStrategy -> simulated orders
                            | entry proposal
                            v
                    FastAPI risk gate <-> PostgreSQL ledger
                       ^            ^
       engine/account snapshots    optional TradingAgents 0.7.1 research
                       |
                read-only OpenClaw client

FreqUI: bundled in the official Freqtrade image
QuantStats: optional report generator from recorded paper equity
```

Freqtrade remains the sole order engine. CCXT comes through Freqtrade; it is not a second order path. Research never receives engine/admin credentials and cannot submit orders. OpenClaw does not need to remain online for the baseline bot to run.

## Start the paper bot

Prerequisites: Ubuntu, Git, Python 3, Docker Engine with Compose v2, outbound HTTPS, and available local ports 8080/8081. A small deployment needs room for the engine, database and control plane; the optional research container adds memory and API costs. No local GPU is required.

```bash
git clone https://github.com/carvidales/tina.git
cd tina
python3 tools/bootstrap.py
docker compose up -d --build
python3 tools/control.py status
docker compose logs --tail=100 freqtrade control
```

`bootstrap.py` generates unique credentials into mode-0600 `.env`, plus an empty `.env.research`. It refuses to overwrite existing credentials. Never commit or paste either file. Once this branch is merged, cloning the default branch is sufficient.

The engine loads public exchange data, calculates its strategy and executes qualifying trades automatically **in simulation**. It may legitimately have no entries for extended periods. `ready: true` confirms fresh reconciliation and no entry halt; it does not mean the strategy is profitable or has an active signal. An initial reconciliation error is expected while the engine starts. Persistent errors require inspection, not bypassing the gate.

### Defaults

| Setting | Initial value |
|---|---|
| Venue / markets | Kraken spot; BTC/EUR and ETH/EUR |
| Candle timeframe | 15 minutes |
| Simulated wallet | EUR 1,000 |
| Maximum proposed order | EUR 100, further reduced by risk sizing |
| Open positions | At most 2; one position per asset |
| Exposure caps | 20% per asset, 40% aggregate |
| Planned trade-risk budget | 0.5% of observed equity |
| Strategy stop / ROI threshold | -2% / +3%; additional trend exit |
| New-entry loss breakers | 2% daily equity loss; 5% peak-to-current drawdown |
| Quote / account observation expiry | 20 seconds / 30 seconds |
| AI policy | `shadow`, no influence on entries |

These are illustrative engineering limits, not optimized investment parameters. Planned risk includes a 1.2% round-trip fee/slippage allowance; this is **not** an exchange fee quote or a maximum possible loss. Fills, gaps, latency and outages can be worse. Freqtrade's simulation fees and this policy allowance serve different purposes.

## Dashboard and operator controls

FreqUI is bound to localhost port 8080. Login is `tina`, with `TINA_FREQTRADE_PASSWORD` from your local `.env`. From another computer use an SSH tunnel rather than opening firewall ports:

```bash
ssh -L 8080:127.0.0.1:8080 -L 8081:127.0.0.1:8081 carlos@YOUR_SERVER
```

Open `http://localhost:8080` in your browser. The risk API is on localhost port 8081 and is authenticated except for a minimal liveness endpoint.

```bash
python3 tools/control.py status
python3 tools/control.py halt --reason 'Operator maintenance'
python3 tools/control.py resume
```

**Halt stops new grants, not existing positions or already-pending orders.** Exits stay under Freqtrade's stop/ROI/exit logic. A resume cannot reset the ledger or bypass a breached loss limit. Never describe a process stop as a guaranteed position liquidation.

## Optional AI research

Set `TINA_LLM_PROVIDER`, `TINA_QUICK_MODEL` and `TINA_DEEP_MODEL` in `.env` to a provider and model IDs supported by TradingAgents. Put only that provider's API key in `.env.research`; see `.env.research.example`. Set a provider-side spending cap before enabling it.

```bash
docker compose --profile research up -d --build research
docker compose logs --tail=100 research
```

The adapter calls the upstream crypto pipeline explicitly with `asset_type="crypto"`. It analyzes BTC-USD/ETH-USD for contextual research, not exchange-specific EUR execution prices. Runs have bounded debate/tool rounds, output tokens, retries and a process deadline. These controls are **not** a guaranteed monetary budget.

In `shadow` mode reports are stored for comparison but do not affect execution. With `TINA_AI_POLICY=filter` and a recreated control container, a fresh Buy/Overweight report is an additional requirement; absent, expired, failed or other ratings block new entries. AI can veto a baseline signal but cannot create one, raise limits, change code, grant orders or block protective exits. Validate this change separately before keeping it enabled.

```bash
docker compose up -d --force-recreate control
```

## OpenClaw connection

Copy only `tools/openclaw_client.py` to an agent-readable location. Give the OpenClaw process **only** `TINA_READ_TOKEN` and optionally `TINA_CONTROL_URL`. Then allow narrowly scoped calls to:

```bash
python3 /path/to/openclaw_client.py status
python3 /path/to/openclaw_client.py research
python3 /path/to/openclaw_client.py decisions
```

This bridge reads JSON; it does not install or reconfigure OpenClaw, create a messaging schedule, or submit trades. OpenClaw can use these results in its existing notifications. Keep the deployment directory, `.env`, Docker socket/group and sudo privileges inaccessible to its service user. Separate Unix users or VMs are required for meaningful isolation: two processes sharing an unrestricted account are not a security boundary. See [operations](OPERATIONS.md).

## Validation and reporting

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
python -m pytest
```

GitHub Actions runs unit tests, Compose validation, container builds, optional dependency import checks, an actual Freqtrade strategy-load check and a PostgreSQL/control-plane boot check. It never uses LLM credentials or places exchange orders. A workflow being present does not prove its latest run passed: inspect the checks on the pull request.

For historical testing, [VALIDATION.md](VALIDATION.md) includes Kraken trade-history download, backtesting, bias checks, failure drills and promotion gates. **The historical backtest evaluates the baseline, not the external risk service or AI filter.** Those need separate forward testing.

After sufficient recorded equity history, generate an optional report:

```bash
docker compose --profile reports run --rm reports
mkdir -p reports
docker compose --profile reports run --rm --entrypoint cat reports /app/reports/paper-performance.html > reports/paper-performance.html
```

Reports require at least 31 daily observations, do not fill missing days, and use 365 annual periods. Results are simulated, not a live track record. Engine order/fill history is stored in its persistent SQLite volume; control decisions, equity and research are stored in PostgreSQL.

## Limits and next release

Live execution is intentionally **not implemented as a configuration toggle**. The [live-readiness checklist](VALIDATION.md#live-readiness) covers the additional exchange reconciliation, native stops, deployment review and small-capital pilot needed before that release. Do not remove the three paper-only guards to bypass it.

The current baseline is an EMA trend-cross strategy with an RSI filter. It is intentionally simple and unproven. The design does not add FinGPT, Hummingbot, NautilusTrader or another backtester beside the engine; duplicated execution paths would increase complexity without establishing an edge.

Upstream versions, API contracts and source links are recorded in [UPSTREAM.md](UPSTREAM.md).
