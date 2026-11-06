"""CI-only database contract test; local environments without PostgreSQL skip it."""
import os
from concurrent.futures import ThreadPoolExecutor
import pytest
from tina.models import Entry
from tina.risk import Risk
from tina.settings import Policy
from tina.store import Store, metadata


@pytest.mark.skipif(not os.environ.get("TINA_TEST_DATABASE_URL"), reason="disposable PostgreSQL URL not supplied")
def test_independent_workers_serialize_grants(snapshot, now):
    stores = [Store(os.environ["TINA_TEST_DATABASE_URL"]) for _ in range(8)]
    try:
        risks = [Risk(store, Policy()) for store in stores]
        risks[0].snapshot(snapshot, now)
        def grant(i):
            entry = Entry(request_id=f"{i:032x}", pair="BTC/EUR", amount=0.002, rate=50000)
            return risks[i].authorize(entry, now)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(grant, range(8)))
        assert sum(result["allowed"] for result in results) == 1
    finally:
        metadata.drop_all(stores[0].engine)  # Only use a disposable test database.
        for store in stores:
            store.engine.dispose()
