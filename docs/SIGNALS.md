# Simple trade signals

Run one command. Get **WAIT** or **TRADE SETUP**, with the chart timeframes,
entry price, stop-loss, take-profit and entry deadline. You decide whether to
place the trade manually. This program cannot buy, sell, or access your account.

## Start

Use Ubuntu's Python 3.10 or newer. No pip install, .env file, database, Docker,
Kraken account or LLM key is needed for this mode.

```bash
python3 tools/signals.py
```

This checks BTC/EUR and ETH/EUR on Kraken. To check just one:

```bash
python3 tools/signals.py --pair BTC/EUR
```

It runs **once**. Run again for a fresh assessment. It does not install a daemon,
configure WhatsApp, schedule alerts, or stop any previously started bot.

## What you receive

If the rules do not match:

```text
BTC/EUR - WAIT
No new trade.
Reason: No confirmed 15-minute breakout
Checked: <date and local time>
Next check: <date and local time>
```

A qualifying setup includes:

```text
BTC/EUR - TRADE SETUP
Direction: BUY (spot, manual execution)
Timeframes: 1 hour trend / 15 minute entry
Entry: EUR <calculated price> (limit; do not pay more)
Stop-loss: EUR <calculated price>
Take-profit: EUR <calculated price>
Entry expires: <date and local time>
Maximum holding: 4 hours from fill; close manually sooner at stop/target
Reward/risk: <ratio before costs and ratio with assumed costs>
Cancel: <invalidation conditions>
```

These placeholders describe the format, not a current trade. The program
fills them only from a valid public-data response. Times use Europe/Madrid
by default; `--timezone UTC` changes the display. It does not predict when a
price target will be reached. Four hours is a strategy time limit, not a forecast.

**WAIT means no NEW entry. It is not advice to cancel a stop or keep an existing
losing position.** This read-only checker has no knowledge of your positions,
account balance, fills or previous actions. Do not add to an existing position
because it prints another setup. The stable signal ID helps you recognize repeats.
A fresh run may update levels; never use it to move an existing protective stop.

## The initial rules (experimental, not validated for profitability)

This is a separate `signals-v1` trend-breakout baseline, NOT the old paper bot's
EMA-cross strategy. Previous bot tests/backtests do not validate this strategy.
It uses no AI predictions and makes no claim of a profitable edge.

- Only BUY spot setups on BTC/EUR and ETH/EUR; no shorts, futures or leverage.
- At least 600 contiguous, finished candles per timeframe. The last uncommitted
  Kraken OHLC row is excluded. Missing/stale/invalid data results in WAIT with
  `data_error: true`, which differs from a valid market assessment with no setup.
- 1-hour close above EMA20 above EMA50 above EMA200.
- Latest completed 15-minute close above the preceding 20 candle highs, with
  volume at least the preceding 20-candle average.
- Quote spread at most 0.2%; current ask within 0.2% of the breakout close.
- Entry at the observed ask rounded up to the market tick, a limit-price cap,
  not a guaranteed fill. Recheck immediately before entry; do not chase a higher
  quote. A price below the stop or a target already touched invalidates the plan.
- Stop below the lower of the last five candle lows and entry minus two ATR14.
  ATR uses Wilder smoothing on finished 15-minute bars. Allowed stop distance:
  0.5%-4%. Take-profit is three times that distance above entry, tick-rounded.
- A 1.2% round-trip fee/slippage buffer is an illustrative assumption, NOT the
  user's actual fees or a maximum possible cost. Reject estimated net reward/risk
  below 1:1. This ratio is not a probability or evidence of positive expectancy.
- Entry expires five minutes after the signal candle closes. Refreshing does not
  extend this deadline. After a fill, close manually at stop/target or after four
  hours. The script does not monitor or execute those exits for you.

A candidate target is a mathematical level, not a forecast or independently
verified resistance level. Stops can execute worse than planned, costs vary,
and any setup can lose. Paper-test and record the signals before relying on them.

## Connect to Tina / OpenClaw

Give Tina permission to run only this read-only command when you ask for signals:

```bash
python3 /absolute/path/to/tina/tools/signals.py --json
```

Instruction for Tina:

> When I ask for a crypto setup, run this checker. Return WAIT with the reason,
> or return the pair, BUY direction, trend and entry timeframes, entry price,
> stop-loss, take-profit, entry expiry, maximum holding time and invalidation
> conditions exactly as returned. Include the checked time. Do not invent levels,
> convert WAIT into a trade, repeat an expired signal, or place orders. State that
> data is unavailable when data_error is true. These are new-entry signals, not
> management of my existing positions.

This is an integration instruction, not a deployed OpenClaw configuration. No
OpenClaw token is needed for this checker. Keep account/exchange secrets out of
its environment. Existing WhatsApp transport is unchanged; no messages are sent
by this script. Any later recurring schedule should scan just after candle closes
and deduplicate `signal_id` before sending a notification.

## Tests and diagnostics

```bash
python3 -m unittest discover -s signal_tests -v
python3 -m py_compile tools/signals.py
```

Exit code 0: completed market assessment, either WAIT or TRADE SETUP.
Exit code 2: data/clock/network/argument problem. Do not treat an outage as a
confident assessment that the market is quiet. The output includes no trade
levels for the failed market. No current signal is cached or reused on failure.

No package dependencies are needed. To retry an outage, run the command again
later. Fix time synchronization if Ubuntu and Kraken disagree by over 30 seconds.
The original paper bot and its dependencies are unchanged and are not started by
this command. Its read-only API bridge is not required for signal mode.

## Source contracts verified for this implementation

- Kraken [OHLC](https://docs.kraken.com/api/docs/rest-api/get-ohlc-data): the final
  row is uncommitted; a request returns at most 720 recent records.
- Kraken [order book](https://docs.kraken.com/api/docs/rest-api/get-order-book):
  public level-2 bids and asks. Level timestamps describe level changes, not the
  time the whole snapshot was fetched.
- Kraken [server time](https://docs.kraken.com/api/docs/rest-api/get-server-time).
- Kraken [asset pairs](https://docs.kraken.com/api/docs/rest-api/get-tradable-asset-pairs):
  market identity, status and tick size.

Only five fixed public GET endpoints are allowed: Time, SystemStatus,
AssetPairs, OHLC and Depth. No private trading endpoints, secrets, dynamic code,
shell subprocesses or order submission are used.
