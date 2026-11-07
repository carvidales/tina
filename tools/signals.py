#!/usr/bin/env python3
"""Read-only crypto setups. Python 3.10+, standard library, no keys or orders."""
import argparse
import json
import math
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

PAIRS = {"BTC/EUR": "XBTEUR", "ETH/EUR": "ETHEUR"}
VERSION = "signals-v1"
COST_BUFFER = 0.012  # Illustrative round-trip fee/slippage allowance, NOT a fee quote.
DISCLAIMER = "Experimental rules, not a proven edge. Manual spot entries only; no orders placed."


class DataError(ValueError):
    pass


def number(value, positive=True):
    if isinstance(value, bool):
        raise DataError("Invalid numeric data")
    value = float(value)
    if not math.isfinite(value) or (value <= 0 if positive else value < 0):
        raise DataError("Invalid numeric data")
    return value


def public_get(endpoint, **params):
    """Only public, fixed-host GETs. No credentials, .env loading or trading API."""
    if endpoint not in {"Time", "SystemStatus", "AssetPairs", "OHLC", "Depth"}:
        raise DataError("Endpoint is not public market data")
    url = "https://api.kraken.com/0/public/" + endpoint
    if params:
        url += "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={
        "User-Agent": "tina-signals/1.0", "Accept": "application/json", "Cache-Control": "no-cache"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=8) as response:
        if urllib.parse.urlparse(response.geturl()).hostname != "api.kraken.com":
            raise DataError("Unexpected market-data host")
        stamp = parsedate_to_datetime(response.headers["Date"]).timestamp()
        if abs(time.time() - stamp) > 60:
            raise DataError("Stale HTTP response or incorrect server clock")
        body = response.read(2_000_001)
    if len(body) > 2_000_000:
        raise DataError("Market-data response is too large")
    document = json.loads(body)
    if document.get("error") or not isinstance(document.get("result"), dict):
        raise DataError("Market-data provider returned an error")
    return document["result"]


def only_pair(result):
    values = [value for key, value in result.items() if key != "last"]
    if len(values) != 1:
        raise DataError("Ambiguous market-data response")
    return values[0]


def closed_bars(result, minutes, now):
    rows = only_pair(result)
    if not isinstance(rows, list) or len(rows) < 2:
        raise DataError("Missing price history")
    # Kraken documents the final row as uncommitted, even when 'since' is used.
    bars = []
    for row in rows[:-1]:
        if not isinstance(row, list) or len(row) != 8:
            raise DataError("Malformed candle")
        stamp = number(row[0])
        op, high, low, close = [number(value) for value in row[1:5]]
        volume = number(row[6], positive=False)
        if stamp != int(stamp) or stamp % (minutes * 60):
            raise DataError("Candle timestamp is off the expected grid")
        if low > min(op, close) or high < max(op, close) or low > high:
            raise DataError("Invalid candle prices")
        if stamp + minutes * 60 > now:
            raise DataError("Future or unfinished candle")
        if bars and stamp - bars[-1][0] != minutes * 60:
            raise DataError("Missing or duplicate candles")
        bars.append((int(stamp), op, high, low, close, volume))
    expected = (int(now) // (minutes * 60) - 1) * minutes * 60
    if len(bars) < 600 or bars[-1][0] != expected:
        raise DataError("Insufficient or stale closed-candle history")
    return bars


def ema(values, span):
    result = values[0]
    alpha = 2 / (span + 1)
    for value in values[1:]:
        result += alpha * (value - result)
    return result


def atr(bars):
    # Wilder smoothing; history contains only closed bars.
    values = [max(b[2] - b[3], abs(b[2] - p[4]), abs(b[3] - p[4]))
              for p, b in zip(bars, bars[1:])]
    result = sum(values[:14]) / 14
    for value in values[14:]:
        result = (result * 13 + value) / 14
    return result


def level(value, tick, up=False):
    tick = Decimal(str(tick))
    number(tick)
    rounded = (Decimal(str(value)) / tick).to_integral_value(
        rounding=ROUND_CEILING if up else ROUND_FLOOR) * tick
    return format(rounded, "f")


def iso(stamp):
    return datetime.fromtimestamp(stamp, timezone.utc).isoformat(timespec="seconds")


def wait(pair, reason, now, error=False):
    return {"pair": pair, "action": "WAIT", "reason": reason, "data_error": error,
            "as_of": iso(now), "trend_timeframe": "1h", "entry_timeframe": "15m",
            "next_check": iso((int(now) // 900 + 1) * 900 + 15),
            "strategy": VERSION, "disclaimer": DISCLAIMER}


def evaluate(pair, hourly, intraday, bid, ask, tick, now):
    """Pure rule evaluation. Output is a proposed plan, never an execution command."""
    h = closed_bars(hourly, 60, now)
    m = closed_bars(intraday, 15, now)
    bid, ask = number(bid), number(ask)
    number(tick)
    if bid > ask or (ask - bid) / bid > 0.002:
        return wait(pair, "Spread is too wide or the quote is invalid", now)
    prices = [b[4] for b in h]
    if not (prices[-1] > ema(prices, 20) > ema(prices, 50) > ema(prices, 200)):
        return wait(pair, "The 1-hour uptrend filter is not met", now)
    latest, previous = m[-1], m[-21:-1]
    if latest[4] <= max(b[2] for b in previous) or latest[5] <= 0:
        return wait(pair, "No confirmed 15-minute breakout", now)
    if latest[5] < sum(b[5] for b in previous) / len(previous):
        return wait(pair, "Breakout volume is below its recent average", now)
    # A closed-bar setup expires five minutes after that bar, not after each request.
    expires = latest[0] + 900 + 300
    if now >= expires:
        return wait(pair, "The entry window has expired; wait for a fresh setup", now)
    if abs(ask / latest[4] - 1) > 0.002:
        return wait(pair, "Price moved away from the signal; do not chase", now)
    entry = level(ask, tick, up=True)
    stop = level(min(min(b[3] for b in m[-5:]), float(entry) - 2 * atr(m)), tick)
    risk = float(entry) - float(stop)
    distance = risk / float(entry)
    if float(stop) <= 0 or not 0.005 <= distance <= 0.04:
        return wait(pair, "The stop distance is outside the strategy limits", now)
    target = level(float(entry) + 3 * risk, tick, up=True)
    cost = float(entry) * COST_BUFFER
    net_rr = (float(target) - float(entry) - cost) / (risk + cost)
    if net_rr < 1:
        return wait(pair, "Reward is insufficient after the assumed trading costs", now)
    return {"pair": pair, "action": "TRADE_SETUP", "direction": "BUY_SPOT",
            "entry": entry, "stop_loss": stop, "take_profit": target,
            "entry_type": "Limit buy at the stated price or better; do not chase",
            "trend_timeframe": "1h", "entry_timeframe": "15m",
            "entry_valid_until": iso(expires), "maximum_holding_hours": 4,
            "gross_reward_risk": round((float(target) - float(entry)) / risk, 3),
            "estimated_net_reward_risk": round(net_rr, 3),
            "assumed_round_trip_cost_pct": COST_BUFFER * 100,
            "reason": "1h uptrend and a closed 15m breakout with volume confirmation",
            "as_of": iso(now), "signal_id": f"{VERSION}:{pair}:{latest[0]}",
            "next_check": iso((int(now) // 900 + 1) * 900 + 15),
            "cancel_if": "Expired, stop/target touched before entry, or price above entry; refresh first",
            "position_note": "Only for a new position. Do not add if already holding this trade",
            "strategy": VERSION, "disclaimer": DISCLAIMER}


def scan(pair, fetch=public_get, clock=time.time):
    """Errors are distinguishable WAIT responses, never a recycled trade signal."""
    try:
        if pair not in PAIRS:
            raise DataError("Unsupported pair")
        server_time = number(fetch("Time")["unixtime"])
        if abs(clock() - server_time) > 30:
            raise DataError("Local clock differs from the exchange; synchronize Ubuntu time")
        if fetch("SystemStatus").get("status") != "online":
            raise DataError("The exchange is not fully online")
        symbol = PAIRS[pair]
        meta = only_pair(fetch("AssetPairs", pair=symbol))
        if meta.get("wsname", "").replace("XBT", "BTC") != pair:
            raise DataError("Market identity does not match")
        if meta.get("status") != "online":
            raise DataError("The selected market is not online")
        tick = meta["tick_size"]
        hourly = fetch("OHLC", pair=symbol, interval=60)
        intraday = fetch("OHLC", pair=symbol, interval=15)
        quote_started = clock()
        depth = only_pair(fetch("Depth", pair=symbol, count=1))
        now = clock()
        if not 0 <= now - quote_started <= 10:
            raise DataError("Quote retrieval was too slow or the clock changed")
        # Timestamps on levels are last changes, NOT snapshot timestamps.
        return evaluate(pair, hourly, intraday, depth["bids"][0][0],
                        depth["asks"][0][0], tick, now)
    except Exception as exc:
        message = str(exc) if isinstance(exc, DataError) else type(exc).__name__
        return wait(pair, "Data unavailable or invalid: " + message, clock(), error=True)


def display(result, tz="Europe/Madrid"):
    zone = ZoneInfo(tz)
    def local(value):
        return datetime.fromisoformat(value).astimezone(zone).strftime("%Y-%m-%d %H:%M:%S %Z")
    lines = [f"{result['pair']} - {result['action'].replace('_', ' ')}"]
    if result["action"] == "WAIT":
        lines += ["No new trade.", "Reason: " + result["reason"]]
    else:
        lines += ["Direction: BUY (spot, manual execution)",
                  "Timeframes: 1 hour trend / 15 minute entry",
                  f"Entry: EUR {result['entry']} (limit; do not pay more)",
                  f"Stop-loss: EUR {result['stop_loss']}",
                  f"Take-profit: EUR {result['take_profit']}",
                  "Entry expires: " + local(result["entry_valid_until"]),
                  "Maximum holding: 4 hours from fill; close manually sooner at stop/target",
                  f"Reward/risk: {result['gross_reward_risk']}:1 before costs; "
                  f"{result['estimated_net_reward_risk']}:1 with assumed 1.2% costs",
                  "Cancel: " + result["cancel_if"],
                  result["position_note"], "Reason: " + result["reason"],
                  "Signal ID: " + result["signal_id"]]
    lines += ["Checked: " + local(result["as_of"]), "Next check: " + local(result["next_check"])]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair", choices=list(PAIRS), help="Default: check BTC/EUR and ETH/EUR")
    parser.add_argument("--json", action="store_true", help="Structured results for Tina/OpenClaw")
    parser.add_argument("--timezone", default="Europe/Madrid")
    args = parser.parse_args(argv)
    try:
        ZoneInfo(args.timezone)
    except (KeyError, ValueError):
        parser.error("Unknown timezone; use UTC or install Ubuntu tzdata")
    results = [scan(pair) for pair in ([args.pair] if args.pair else PAIRS)]
    # Never print a setup that expired while a later market was being checked.
    now = time.time()
    for i, item in enumerate(results):
        if item["action"] == "TRADE_SETUP" and (
                datetime.fromisoformat(item["entry_valid_until"]).timestamp() <= now
                or now - datetime.fromisoformat(item["as_of"]).timestamp() > 30):
            results[i] = wait(item["pair"], "Setup expired during this scan; run again", now)
    print(json.dumps(results, indent=2, allow_nan=False) if args.json else
          "\n\n".join(display(item, args.timezone) for item in results) + "\n\n" + DISCLAIMER)
    return 2 if any(item.get("data_error") for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
