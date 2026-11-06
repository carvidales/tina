"""Unproven trend baseline; every forward entry requires an external risk grant."""
import json
import logging
import math
import os
import urllib.request
import uuid
from datetime import datetime
from pandas import DataFrame
from freqtrade.strategy import IStrategy

log = logging.getLogger(__name__)


class TinaStrategy(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "15m"
    can_short = False
    startup_candle_count = 600
    process_only_new_candles = True
    position_adjustment_enable = False
    minimal_roi = {"0": 0.03}
    stoploss = -0.02
    trailing_stop = False
    use_exit_signal = True

    @property
    def protections(self):
        return [{"method": "CooldownPeriod", "stop_duration_candles": 4},
                {"method": "StoplossGuard", "lookback_period_candles": 24,
                 "trade_limit": 2, "stop_duration_candles": 16, "only_per_pair": False}]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        for window in (20, 50, 200):
            dataframe[f"ema{window}"] = dataframe["close"].ewm(span=window, adjust=False).mean()
        delta = dataframe["close"].diff()
        up = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
        down = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
        dataframe["rsi"] = 100 - 100 / (1 + up / down.replace(0, float("nan")))
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[(dataframe["ema20"] > dataframe["ema50"])
                      & (dataframe["ema20"].shift(1) <= dataframe["ema50"].shift(1))
                      & (dataframe["close"] > dataframe["ema200"])
                      & dataframe["rsi"].between(40, 70) & (dataframe["volume"] > 0),
                      ["enter_long", "enter_tag"]] = (1, "trend_cross")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[((dataframe["ema20"] < dataframe["ema50"]) | (dataframe["rsi"] > 80))
                      & (dataframe["volume"] > 0), "exit_long"] = 1
        return dataframe

    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake,
                            min_stake, max_stake, leverage, entry_tag, side, **kwargs):
        try:
            equity = self.wallets.get_total_stake_amount()
            stake = min(proposed_stake, max_stake, 100.0, equity * 0.20, equity * 0.005 / 0.032)
            return stake if math.isfinite(stake) and stake >= (min_stake or 0) and stake > 0 else 0
        except Exception:
            return 0  # Raising here can make Freqtrade fall back to proposed_stake.

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time: datetime, entry_tag,
                            side: str, **kwargs) -> bool:
        mode = getattr(self.config.get("runmode"), "value", self.config.get("runmode"))
        if mode in ("backtest", "hyperopt"):
            # Historical baseline only: external risk and AI are NOT replayed here.
            return side == "long" and pair in ("BTC/EUR", "ETH/EUR")
        if self.config.get("dry_run") is not True or mode != "dry_run" or side != "long":
            return False
        try:
            if order_type != "limit" or not all(math.isfinite(x) and x > 0 for x in (amount, rate)):
                return False
            token = os.environ["TINA_ENGINE_TOKEN"]
            if len(token) < 32:
                return False
            request_id = uuid.uuid4().hex
            body = {"request_id": request_id, "pair": pair, "side": side, "amount": amount, "rate": rate}
            request = urllib.request.Request(
                os.environ.get("TINA_CONTROL_URL", "http://control:8081") + "/v1/entries/authorize",
                data=json.dumps(body, allow_nan=False).encode(), method="POST",
                headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
            # An ambiguous timeout means NO entry. Never retry a grant automatically.
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(request, timeout=2) as response:
                result = json.loads(response.read(8192))
            return result.get("allowed") is True and result.get("request_id") == request_id
        except Exception as exc:
            log.warning("Entry denied: risk service unavailable (%s)", type(exc).__name__)
            return False

    # Exits never depend on the AI or control service; engine stop/ROI/exit logic stays active.
