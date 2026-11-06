# Validation and promotion

## Historical baseline

Kraken's candle endpoint is limited for older history. Freqtrade documents downloading historical trades with `--dl-trades`; do not assume a requested date range means all candles were retrieved. Verify coverage, missing intervals and warmup separately.

Example commands, with dates deliberately left for the operator to select before examining outcomes:

```bash
# Define an actual historical interval, e.g. YYYYMMDD-YYYYMMDD.
export TIMERANGE=YOUR_CHRONOLOGICAL_INTERVAL
docker compose run --rm --no-deps freqtrade download-data --pairs BTC/EUR ETH/EUR --timeframes 15m --timerange "$TIMERANGE" --dl-trades
docker compose run --rm --no-deps freqtrade backtesting --timerange "$TIMERANGE" --enable-protections --export trades
docker compose run --rm --no-deps freqtrade lookahead-analysis --timerange "$TIMERANGE"
docker compose run --rm --no-deps freqtrade recursive-analysis --timerange "$TIMERANGE"
```

These commands do not constitute completed backtests. Kraken trade downloads can be large; use a bounded period, verify disk space, and consult upstream bulk-history guidance. The entry callback bypasses the online gate in backtest/hyperopt modes: baseline results do not include the independent risk ledger, live reconciliation, LLM decisions or API costs.

Use chronological training, validation and untouched test periods. Record the data snapshot, code revision, tested parameters and all failed candidates. Test higher fees, adverse slippage, latency, sparse data and several market regimes. Compare against cash and appropriate buy-and-hold baselines. Do not repeatedly tune on the final holdout. Passing a lookahead check is not proof that there is no bias or that the strategy is profitable.

## Forward dry-run

Suggested observation window: at least 30-60 days, and longer when signals are sparse or regimes are narrow. This is not a statistical sufficiency rule. Record trade count, drawdown, net return, exposure, missed fills, rejected entries, data outages, AI costs and baseline-versus-filter results. Preserve decisions at their original timestamps; do not reconstruct news using information published later.

Run and document failure drills in paper mode:

- Stop the control service or PostgreSQL: new entries must fail; engine exits must not call the failed service.
- Interrupt public data: no successful refresh means no new grants; no stale observations may be relabelled as current.
- Restart services during an order: reconcile open orders and positions, retain entry counters/reservations and avoid duplicates.
- Trigger manual halt and simulated loss thresholds: verify persistence and that resume does not reset limits.
- Remove the research API key: shadow mode remains independent; filter mode ultimately blocks expired reports.
- Validate partial fills, rejected/cancelled entries, reservation expiry, exchange precision/minimums and clock changes against actual engine responses.

The test suite exercises unit-level controls with synthetic/mocked inputs. Container CI checks package/configuration integration, not actual exchange fills or a profitable strategy.

## Live-readiness

This release blocks live mode in the launcher, strategy and collector. A live release requires an explicit code review and separate configuration, not editing one Boolean.

Required evidence before enabling a limited pilot:

1. Successful container CI plus a reviewed deployment on the actual Ubuntu host.
2. Adequate out-of-sample and forward results after realistic execution and model costs; documented strategy rejection criteria.
3. Venue-specific authoritative balance, open-order and fill reconciliation; recovery from ambiguous acknowledgements, disconnects and partial fills.
4. Exchange-native stops verified on the selected spot markets, including rejected-stop recovery. Local stops cannot protect a stopped host.
5. Account/subaccount isolation, no withdrawals on the API key, minimum permissions, IP restrictions where available, and a tested secret-rotation process.
6. Deposit/withdrawal-aware equity baselines, marked-to-market risk, precise minimum/step/tick handling and timestamped market-data checks.
7. An emergency procedure distinguishing halt-new-entries, cancel-pending-orders and liquidation. None should be mislabeled as the others.
8. Immutable reviewed deployment artifacts, complete dependency locking/digests, backup/restore rehearsal and independent alerts.
9. Explicit operator authorization and a strictly capped small-capital pilot. Scale only after actual execution evidence, not simulated returns.

These are engineering gates, not a guarantee against loss. Autonomous crypto trading can lose the entire allocated capital. No live order has been validated by the local unit suite.
