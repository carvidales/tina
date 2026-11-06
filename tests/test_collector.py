import pytest
from tina.collector import normalize, number


@pytest.fixture
def raw(now):
    config = dict(dry_run=True, trading_mode="spot", stake_currency="EUR", exchange="kraken",
        strategy="TinaStrategy", timeframe="15m", force_entry_enable=False,
        position_adjustment_enable=False, state="running", max_open_trades=2, stoploss=-0.02)
    balance = {"total": 1000, "currencies": [{"currency": "EUR", "free": 900}]}
    health = {"last_process_ts": now}
    ticker = {"error": [], "result": {"XXBTZEUR": {"a": ["50000"], "b": ["49990"]},
                                       "XETHZEUR": {"a": ["2500"], "b": ["2499"]}}}
    return [config, balance, [], health, ticker, now]


def test_normalize(raw):
    result = normalize(*raw)
    assert result.equity == 1000 and result.cash == 900
    assert result.quotes["BTC/EUR"].ask == 50000


@pytest.mark.parametrize("field,value", [("dry_run", False), ("force_entry_enable", True),
    ("stoploss", -0.50), ("trading_mode", "futures"), ("strategy", "Other"),
    ("stake_currency", "USDT"), ("state", "stopped"), ("max_open_trades", 10)])
def test_configuration_drift(raw, field, value):
    raw[0][field] = value
    with pytest.raises(ValueError):
        normalize(*raw)


def test_pending_entry_exposure(raw):
    raw[2] = [dict(pair="BTC/EUR", is_short=False, leverage=1, amount=0,
        amount_requested=0.002, current_rate=50000, open_rate=50000, stake_amount=100)]
    assert normalize(*raw).exposures == {"BTC/EUR": 100}


def test_missing_position_stop(raw):
    raw[2] = [dict(pair="BTC/EUR", is_short=False, leverage=1, amount=0.002,
        amount_requested=0.002, current_rate=50000, open_rate=50000, stake_amount=100, stop_loss_abs=0)]
    with pytest.raises(ValueError):
        normalize(*raw)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), True, "not money"])
def test_bad_numbers(bad):
    with pytest.raises(ValueError):
        number(bad)
