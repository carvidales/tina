# Upstream components and verification

Source/API review date: 2026-11-06. Source inspection verifies interfaces, not complete security or profitability. No upstream source tree is vendored into TINA; dependencies retain their respective licenses. Review the linked license files before redistribution or commercial integration.

| Component | Integration | Primary source |
|---|---|---|
| Freqtrade | `freqtradeorg/freqtrade:2026.10`; strategy, dry-run, simulation ledger and execution lifecycle | https://github.com/freqtrade/freqtrade/releases/tag/2026.10 |
| FreqUI | Included by the official image's `freqtrade install-ui` build step; no duplicate UI service | https://github.com/freqtrade/freqtrade/blob/2026.10/Dockerfile |
| CCXT | Supplied transitively by Freqtrade; not a separate execution path | https://github.com/freqtrade/freqtrade/blob/2026.10/requirements.txt |
| TradingAgents | Optional package `tradingagents==0.7.1`; explicit crypto pipeline and five-tier/REVIEW rating | https://github.com/TauricResearch/TradingAgents/blob/v0.7.1/tradingagents/graph/trading_graph.py |
| QuantStats | Optional equity report generation; 365 annual periods | https://github.com/ranaroussi/quantstats |
| Kraken | Public spot ticker observations; no authenticated exchange requests | https://docs.kraken.com/api/docs/rest-api/get-ticker-information/ |
| OpenClaw | Fixed-route read-only CLI bridge; no host auto-configuration | https://docs.openclaw.ai/gateway/security |

Reviewed Freqtrade contracts:

- https://github.com/freqtrade/freqtrade/blob/2026.10/freqtrade/rpc/api_server/api_schemas.py
- https://github.com/freqtrade/freqtrade/blob/2026.10/freqtrade/rpc/rpc.py
- https://www.freqtrade.io/en/stable/strategy-callbacks/
- https://www.freqtrade.io/en/stable/rest-api/
- https://www.freqtrade.io/en/stable/exchanges/#historic-kraken-data

TradingAgents configuration and dependencies:

- https://github.com/TauricResearch/TradingAgents/blob/v0.7.1/tradingagents/default_config.py
- https://github.com/TauricResearch/TradingAgents/blob/v0.7.1/pyproject.toml
- https://github.com/TauricResearch/TradingAgents/releases/tag/v0.7.1

Licenses: https://github.com/freqtrade/freqtrade/blob/2026.10/LICENSE and https://github.com/TauricResearch/TradingAgents/blob/v0.7.1/LICENSE. Other libraries' licenses remain upstream.

## Reproducibility limits

Direct application dependencies and the two central trading/research releases are selected explicitly. This initial integration does not provide a complete transitive lockfile or image digest pinning: PostgreSQL/Python tags and some optional dependency ranges can resolve differently over time. Container CI detects installation/integration failures; it does not eliminate supply-chain risk. Capture a reviewed lockfile and image digests in the actual network-enabled build environment before any live release.
