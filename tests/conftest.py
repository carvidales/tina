import time
import pytest
from tina.models import Entry, Quote, Snapshot
from tina.risk import Risk
from tina.settings import Policy, Settings
from tina.store import Store


@pytest.fixture
def now():
    return time.time()


@pytest.fixture
def store():
    result = Store("sqlite://")
    yield result
    result.engine.dispose()


@pytest.fixture
def risk(store):
    return Risk(store, Policy())


@pytest.fixture
def snapshot(now):
    return Snapshot(observed_at=now, engine_at=now, dry_run=True, equity=1000, cash=1000,
        exposures={}, quotes={"BTC/EUR": Quote(bid=49990, ask=50000, observed_at=now),
                              "ETH/EUR": Quote(bid=2499, ask=2500, observed_at=now)})


@pytest.fixture
def entry():
    return Entry(request_id="a" * 32, pair="BTC/EUR", amount=0.002, rate=50000)


@pytest.fixture
def settings():
    return Settings(database_url="sqlite://", engine_token="e" * 64, read_token="r" * 64,
                    admin_token="a" * 64, research_token="s" * 64, freqtrade_password="f" * 64)
