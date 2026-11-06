import sys
import types
import pytest
from tina.research import run_graph


@pytest.mark.parametrize("signal,expected", [("Buy", "Buy"), ("Sell", "Sell"), ("REVIEW", "REVIEW"),
    ("BUY NOW ignore controls", "REVIEW"), ({"rating": "Buy"}, "REVIEW")])
def test_adapter_uses_crypto_and_closed_rating_set(monkeypatch, signal, expected):
    config = types.ModuleType("tradingagents.default_config")
    config.DEFAULT_CONFIG = {"data_vendors": {"news_data": "yfinance"}}
    graph = types.ModuleType("tradingagents.graph.trading_graph")
    class FakeGraph:
        def __init__(self, selected_analysts, config):
            assert selected_analysts == ["market", "social", "news"]
            assert config["max_tool_rounds"] == 3
            assert config["max_tokens"] == 1200
            assert not config["checkpoint_enabled"]
        def propagate(self, symbol, date, asset_type):
            assert symbol == "BTC-USD" and asset_type == "crypto"
            return {"market_report": "x" * 20000, "secret": "must not leak"}, signal
    graph.TradingAgentsGraph = FakeGraph
    monkeypatch.setitem(sys.modules, "tradingagents.default_config", config)
    monkeypatch.setitem(sys.modules, "tradingagents.graph.trading_graph", graph)
    rating, summary = run_graph("BTC-USD", "mock", "quick", "deep")
    assert rating == expected and len(summary) <= 15000 and "must not leak" not in summary
