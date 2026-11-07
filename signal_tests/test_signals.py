"""Offline tests; no installation, Docker, network, credentials or trade APIs."""
import contextlib
import copy
import importlib.util
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("signals", Path(__file__).resolve().parents[1] / "tools/signals.py")
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)
NOW = 1_800_000_000 // 3600 * 3600 + 60


def history(minutes, trend=False):
    end = NOW // (minutes * 60) * minutes * 60
    rows = []
    for i in range(601):
        price = 40 + i * 0.1 if trend else 100
        rows.append([end - (600 - i) * minutes * 60, str(price), str(price + .5),
                     str(price - .5), str(price), str(price), "100", 10])
    if not trend:
        rows[-2][2] = "101.2"
        rows[-2][4] = "101"
        rows[-2][6] = "200"
    return {"XXBTZEUR": rows, "last": end}


class SignalsTests(unittest.TestCase):
    def setUp(self):
        self.h = history(60, True)
        self.m = history(15)

    def evaluate(self, **changes):
        args = dict(pair="BTC/EUR", hourly=self.h, intraday=self.m,
                    bid=101, ask=101.01, tick="0.1", now=NOW)
        args.update(changes)
        return s.evaluate(**args)

    def fetch(self, endpoint, **kwargs):
        if endpoint == "Time": return {"unixtime": NOW}
        if endpoint == "SystemStatus": return {"status": "online"}
        if endpoint == "AssetPairs":
            return {"XXBTZEUR": {"wsname": "XBT/EUR", "tick_size": "0.1", "status": "online"}}
        if endpoint == "OHLC": return self.h if kwargs["interval"] == 60 else self.m
        if endpoint == "Depth":
            return {"XXBTZEUR": {"bids": [["101", "1", NOW]], "asks": [["101.01", "1", NOW]]}}
        raise AssertionError("An unapproved endpoint was used")

    def test_complete_setup_and_tick_rounding(self):
        result = self.evaluate()
        self.assertEqual(result["action"], "TRADE_SETUP")
        self.assertEqual(result["entry"], "101.1")
        self.assertLess(float(result["stop_loss"]), float(result["entry"]))
        self.assertGreater(float(result["take_profit"]), float(result["entry"]))
        self.assertGreaterEqual(result["gross_reward_risk"], 3)
        self.assertGreaterEqual(result["estimated_net_reward_risk"], 1)
        self.assertEqual(result["trend_timeframe"], "1h")
        self.assertEqual(result["entry_timeframe"], "15m")
        self.assertEqual(result["maximum_holding_hours"], 4)

    def test_zero_secrets_public_integration(self):
        result = s.scan("BTC/EUR", self.fetch, lambda: NOW)
        self.assertEqual(result["action"], "TRADE_SETUP")

    def test_flat_trend_wait(self):
        flat = history(60)
        flat["XXBTZEUR"][-2][4] = "100"
        self.assertEqual(self.evaluate(hourly=flat)["action"], "WAIT")

    def test_no_breakout_wait(self):
        self.m["XXBTZEUR"][-2][4] = "100"
        self.assertEqual(self.evaluate()["action"], "WAIT")

    def test_weak_volume_wait(self):
        self.m["XXBTZEUR"][-2][6] = "1"
        self.assertIn("volume", self.evaluate()["reason"])

    def test_chasing_price_wait(self):
        self.assertIn("chase", self.evaluate(bid=105, ask=105.01)["reason"])

    def test_wide_or_crossed_quote_wait(self):
        for bid, ask in ((100, 101.01), (102, 101.01)):
            with self.subTest(bid=bid):
                self.assertEqual(self.evaluate(bid=bid, ask=ask)["action"], "WAIT")

    def test_expiry_is_anchored_to_candle(self):
        a = self.evaluate()
        b = self.evaluate(now=NOW + 60)
        self.assertEqual(a["signal_id"], b["signal_id"])
        self.assertEqual(a["entry_valid_until"], b["entry_valid_until"])
        self.assertEqual(self.evaluate(now=NOW + 240)["action"], "WAIT")

    def test_uncommitted_last_bar_is_never_used(self):
        original = self.evaluate()
        self.m["XXBTZEUR"][-1][4] = "nan"
        self.assertEqual(self.evaluate(), original)

    def test_bad_numbers_rejected(self):
        for value in ("NaN", "Infinity", "-Infinity", "0", "-1", True):
            with self.subTest(value=value), self.assertRaises(s.DataError):
                self.evaluate(ask=value)

    def test_bad_ohlc_rejected(self):
        for column, value in ((2, "1"), (3, "200"), (4, "nan"), (6, "-1"), (0, NOW + 3600)):
            with self.subTest(column=column):
                bad = copy.deepcopy(self.m)
                bad["XXBTZEUR"][-2][column] = value
                with self.assertRaises(s.DataError): self.evaluate(intraday=bad)

    def test_insufficient_history_rejected(self):
        self.m["XXBTZEUR"] = self.m["XXBTZEUR"][-100:]
        with self.assertRaises(s.DataError): self.evaluate()

    def test_missing_duplicate_and_stale_bars_rejected(self):
        for mode in ("missing", "duplicate", "stale"):
            bad = copy.deepcopy(self.m)
            if mode == "missing": del bad["XXBTZEUR"][-5]
            if mode == "duplicate": bad["XXBTZEUR"][-5] = bad["XXBTZEUR"][-6]
            if mode == "stale":
                for row in bad["XXBTZEUR"]: row[0] -= 900
            with self.subTest(mode=mode), self.assertRaises(s.DataError):
                self.evaluate(intraday=bad)

    def test_wrong_pair_rejected(self):
        def fetch(endpoint, **kwargs):
            response = self.fetch(endpoint, **kwargs)
            if endpoint == "AssetPairs": response["XXBTZEUR"]["wsname"] = "ETH/EUR"
            return response
        self.assertTrue(s.scan("BTC/EUR", fetch, lambda: NOW)["data_error"])

    def test_maintenance_rejected(self):
        def fetch(endpoint, **kwargs):
            return {"status": "maintenance"} if endpoint == "SystemStatus" else self.fetch(endpoint, **kwargs)
        self.assertEqual(s.scan("BTC/EUR", fetch, lambda: NOW)["action"], "WAIT")

    def test_offline_does_not_reuse_or_invent_prices(self):
        def offline(*args, **kwargs): raise OSError("offline")
        result = s.scan("BTC/EUR", offline, lambda: NOW)
        self.assertTrue(result["data_error"])
        self.assertEqual(result["action"], "WAIT")
        self.assertNotIn("entry", result)

    def test_clock_skew_fails_closed(self):
        result = s.scan("BTC/EUR", self.fetch, lambda: NOW + 120)
        self.assertTrue(result["data_error"])
        self.assertIn("clock", result["reason"])

    def test_invalid_endpoint_blocked_before_network(self):
        with self.assertRaises(s.DataError): s.public_get("AddOrder")

    def test_text_and_json_keep_required_plan(self):
        result = self.evaluate()
        text = s.display(result)
        for field in ("Entry:", "Stop-loss:", "Take-profit:", "Timeframes:", "Entry expires:", "Maximum holding:"):
            self.assertIn(field, text)
        self.assertEqual(json.loads(json.dumps(result, allow_nan=False)), result)

    def test_wait_text_not_an_exit_instruction(self):
        text = s.display(s.wait("BTC/EUR", "No setup", NOW))
        self.assertIn("No new trade", text)
        self.assertNotIn("close", text)

    def test_cli_fails_closed_and_returns_structured_error(self):
        result = s.wait("BTC/EUR", "Offline", NOW, error=True)
        output = io.StringIO()
        with patch.object(s, "scan", return_value=result), contextlib.redirect_stdout(output):
            self.assertEqual(s.main(["--pair", "BTC/EUR", "--json"]), 2)
        self.assertEqual(json.loads(output.getvalue())[0]["action"], "WAIT")

    def test_cli_suppresses_expired_setup(self):
        result = self.evaluate()
        output = io.StringIO()
        with patch.object(s, "scan", return_value=result), patch.object(s.time, "time", return_value=NOW + 400), contextlib.redirect_stdout(output):
            s.main(["--pair", "BTC/EUR", "--json"])
        self.assertEqual(json.loads(output.getvalue())[0]["action"], "WAIT")


if __name__ == "__main__":
    unittest.main()
