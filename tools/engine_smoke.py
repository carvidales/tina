"""Run inside the pinned Freqtrade image; no network or LLM calls are needed."""
from datetime import datetime, timezone
from pandas import DataFrame
from freqtrade.configuration import Configuration
from freqtrade.enums import RunMode
from freqtrade.resolvers import StrategyResolver

config = Configuration({"config": ["/freqtrade/config.json"]}, RunMode.DRY_RUN).get_config()
strategy = StrategyResolver.load_strategy(config)
assert type(strategy).__name__ == "TinaStrategy"
assert strategy.stoploss == -0.02 and not strategy.can_short
frame = DataFrame({"close": [100 + i * 0.01 + i % 7 for i in range(700)], "volume": 1})
frame = strategy.populate_indicators(frame, {})
frame = strategy.populate_entry_trend(frame, {})
frame = strategy.populate_exit_trend(frame, {})
assert {"ema20", "ema50", "ema200", "rsi", "enter_long", "exit_long"}.issubset(frame.columns)
strategy.config["dry_run"] = False
assert strategy.confirm_trade_entry("BTC/EUR", "limit", 0.002, 50000, "GTC",
    datetime.now(timezone.utc), "smoke", "long") is False
print("Pinned Freqtrade strategy import, indicators, and live-mode refusal passed")
