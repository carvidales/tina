"""Read-only engine reconciliation and independent Kraken public quote observations."""
import asyncio
import math
import time
import httpx
from tina.models import Quote, Snapshot
from tina.settings import Settings

PAIRS = {"BTC/EUR": "XXBTZEUR", "ETH/EUR": "XETHZEUR"}


def number(value):
    if isinstance(value, bool):
        raise ValueError("boolean is not a balance")
    n = float(value)
    if not math.isfinite(n):
        raise ValueError("nonfinite account value")
    return n


def normalize(config, balance, trades, health, ticker, observed_at):
    if (config.get("dry_run") is not True or config.get("trading_mode") != "spot"
            or config.get("stake_currency") != "EUR" or config.get("exchange") != "kraken"
            or config.get("strategy") != "TinaStrategy" or config.get("timeframe") != "15m"
            or config.get("force_entry_enable") is not False
            or config.get("position_adjustment_enable") is not False
            or config.get("state") != "running"
            or not 0 < number(config.get("max_open_trades")) <= 2
            or not math.isclose(number(config.get("stoploss")), -0.02, abs_tol=1e-9)):
        raise ValueError("engine configuration is outside the reviewed paper policy")
    if ticker.get("error"):
        raise ValueError("Kraken returned an error")
    quotes = {}
    for pair, code in PAIRS.items():
        row = ticker["result"][code]
        quotes[pair] = Quote(bid=number(row["b"][0]), ask=number(row["a"][0]), observed_at=observed_at)
    exposures = {}
    for trade in trades:
        pair = trade["pair"]
        if (pair not in PAIRS or trade.get("is_short") is not False
                or number(trade.get("leverage", 1)) != 1):
            raise ValueError("unexpected position")
        amount, requested = number(trade["amount"]), number(trade["amount_requested"])
        if min(amount, requested) < 0:
            raise ValueError("negative position")
        mark = max(number(trade["current_rate"]), number(trade["open_rate"]))
        exposure = max(number(trade["stake_amount"]), max(amount, requested) * mark)
        if amount > 0 and number(trade.get("stop_loss_abs")) <= 0:
            raise ValueError("position has no protective stop configured")
        exposures[pair] = exposures.get(pair, 0) + exposure
    cash = next(number(c["free"]) for c in balance["currencies"] if c["currency"] == "EUR")
    return Snapshot(observed_at=observed_at, engine_at=number(health["last_process_ts"]),
                    dry_run=True, equity=number(balance["total"]), cash=cash,
                    exposures=exposures, quotes=quotes)


async def collect(settings: Settings):
    started = time.time()
    async with httpx.AsyncClient(base_url=settings.freqtrade_url + "/", timeout=5,
            auth=(settings.freqtrade_user, settings.freqtrade_password), trust_env=False) as engine:
        async def get(path):
            response = await engine.get(path)
            response.raise_for_status()
            return response.json()
        config, balance, trades, health = await asyncio.gather(
            get("show_config"), get("balance"), get("status"), get("health"))
    # A separate client prevents forwarding engine Basic authentication to the exchange.
    async with httpx.AsyncClient(timeout=5, trust_env=False) as public:
        response = await public.get("https://api.kraken.com/0/public/Ticker",
                                    params={"pair": "XBTEUR,ETHEUR"})
        response.raise_for_status()
    return normalize(config, balance, trades, health, response.json(), started)
