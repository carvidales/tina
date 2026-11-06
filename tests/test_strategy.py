import importlib.util
import json
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def strategy(monkeypatch):
    # Unit tests stub only the base class. Container CI loads the actual pinned engine.
    module = types.ModuleType("freqtrade.strategy")
    module.IStrategy = type("IStrategy", (), {})
    monkeypatch.setitem(sys.modules, "freqtrade.strategy", module)
    spec = importlib.util.spec_from_file_location("tina_test_strategy", ROOT / "user_data/strategies/TinaStrategy.py")
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    obj = loaded.TinaStrategy()
    obj.config = {"dry_run": True, "runmode": "dry_run"}
    return obj


def invoke(strategy):
    return strategy.confirm_trade_entry("BTC/EUR", "limit", 0.002, 50000, "GTC",
        datetime.now(timezone.utc), "test", "long")


def test_live_denied(strategy):
    strategy.config = {"dry_run": False, "runmode": "live"}
    assert not invoke(strategy)


def test_missing_token(strategy, monkeypatch):
    monkeypatch.delenv("TINA_ENGINE_TOKEN", raising=False)
    assert not invoke(strategy)


def test_service_outage(strategy, monkeypatch):
    monkeypatch.setenv("TINA_ENGINE_TOKEN", "e" * 64)
    def fail(*args, **kwargs):
        raise TimeoutError()
    monkeypatch.setattr("urllib.request.build_opener", fail)
    assert not invoke(strategy)


@pytest.mark.parametrize("granted", [True, False, "true"])
def test_exact_grant(strategy, monkeypatch, granted):
    monkeypatch.setenv("TINA_ENGINE_TOKEN", "e" * 64)
    class Response:
        def __init__(self, request): self.request = request
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size):
            body = json.loads(self.request.data)
            return json.dumps({"allowed": granted, "request_id": body["request_id"]}).encode()
    class Opener:
        def open(self, request, timeout):
            assert timeout == 2
            return Response(request)
    monkeypatch.setattr("urllib.request.build_opener", lambda *args: Opener())
    assert invoke(strategy) is (granted is True)


def test_offline_backtest(strategy):
    strategy.config = {"runmode": "backtest", "dry_run": True}
    assert invoke(strategy)


def test_causal_indicators(strategy):
    frame = pd.DataFrame({"close": [100 + i * 0.01 + (i % 7) for i in range(700)], "volume": 1})
    before = strategy.populate_indicators(frame.iloc[:650].copy(), {})
    after = strategy.populate_indicators(frame.copy(), {})
    pd.testing.assert_frame_equal(before, after.iloc[:650])


def test_stake_failure_returns_zero(strategy):
    strategy.wallets = None
    assert strategy.custom_stake_amount("BTC/EUR", None, 50000, 100, 5, 1000, 1, "test", "long") == 0


def test_no_exit_gate(strategy):
    assert "confirm_trade_exit" not in type(strategy).__dict__
