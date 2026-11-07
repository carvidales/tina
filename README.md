# TINA - trade or wait?

A simple, read-only crypto signal checker. It tells you **WAIT** or gives you a
**TRADE SETUP** with the timeframe, entry price, stop-loss and take-profit.
It never places trades.

## Run

On Ubuntu with Python 3.10 or newer, from this repository:

```bash
python3 tools/signals.py
```

No Docker, database, exchange credentials, .env setup or paid AI is needed for
this mode. It checks **BTC/EUR and ETH/EUR on Kraken** using public market data.

A setup includes:

- **Direction and timeframes:** BUY spot, 1-hour trend / 15-minute entry.
- **Exact levels:** limit entry, stop-loss and take-profit in EUR.
- **Timing:** entry deadline and a maximum four-hour holding rule after a fill.
- **Context:** reason, invalidation conditions and reward/risk with cost assumptions.

When the rules are not met, the result is **WAIT** with a reason. Missing or bad
data also produces WAIT, explicitly marked as a data error, never invented prices.

It runs **once**. You place and manage any trade manually. It does not know your
positions or monitor your stops. Do not add to an existing trade because you see
a repeated signal. These experimental rules have **no demonstrated profitable edge**.

## Use with Tina / OpenClaw

```bash
python3 tools/signals.py --json
```

The [simple signals guide](docs/SIGNALS.md) contains a short instruction for Tina
to return the result without inventing levels. WhatsApp and recurring alerts are
not configured automatically. Existing OpenClaw settings are untouched.

## Test

```bash
python3 -m unittest discover -s signal_tests -v
```

The original, more complex paper bot is unchanged. Its instructions are in
[the paper-bot guide](docs/PAPER_BOT.md). Running the signal checker does not
start or stop it. **You do not need that stack for this signal-only workflow.**
