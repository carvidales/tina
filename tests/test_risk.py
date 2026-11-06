import dataclasses
import math
from concurrent.futures import ThreadPoolExecutor
import pytest
from pydantic import ValidationError
from tina.models import Entry, Quote, Research, Snapshot
from tina.risk import Risk
from tina.settings import Policy
from tina.store import Store


def changed(entry, **values):
    return Entry.model_validate({**entry.model_dump(), **values})


def test_no_snapshot_denies(risk, entry, now):
    assert not risk.authorize(entry, now)["allowed"]


def test_valid_and_replay(risk, snapshot, entry, now):
    risk.snapshot(snapshot, now)
    assert risk.authorize(entry, now)["allowed"]
    assert not risk.authorize(entry, now)["allowed"]


def test_simultaneous_reservations(risk, snapshot, entry, now):
    risk.snapshot(snapshot, now)
    requests = [changed(entry, request_id=f"{i:032x}") for i in range(20)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda request: risk.authorize(request, now), requests))
    assert sum(result["allowed"] for result in results) == 1


def test_capacity(risk, snapshot, entry, now):
    risk.snapshot(snapshot, now)
    assert risk.authorize(entry, now)["allowed"]
    assert risk.authorize(changed(entry, request_id="b" * 32, pair="ETH/EUR", rate=2500, amount=0.04), now)["allowed"]
    assert "open position limit" in risk.authorize(changed(entry, request_id="c" * 32), now)["reasons"]


@pytest.mark.parametrize("field,value", [("rate", math.nan), ("rate", math.inf), ("amount", -1),
    ("amount", 0), ("side", "short"), ("pair", "XRP/EUR"), ("request_id", "arbitrary")])
def test_invalid_intents(entry, field, value):
    with pytest.raises(ValidationError):
        changed(entry, **{field: value})


@pytest.mark.parametrize("age", [31, -1])
def test_snapshot_age(risk, snapshot, entry, now, age):
    risk.snapshot(snapshot, now)
    assert not risk.authorize(entry, now + age)["allowed"]


def test_stale_quote(risk, snapshot, entry, now):
    snapshot.quotes["BTC/EUR"].observed_at = now - 21
    risk.snapshot(snapshot, now)
    assert "missing/stale quote" in risk.authorize(entry, now)["reasons"]


def test_heartbeat(risk, snapshot, entry, now):
    snapshot.engine_at = now - 31
    risk.snapshot(snapshot, now)
    assert "engine heartbeat stale" in risk.authorize(entry, now)["reasons"]


def test_failure_invalidates_immediately(risk, snapshot, entry, now):
    risk.snapshot(snapshot, now)
    risk.invalidate("ConnectionError")
    assert "reconciliation unavailable" in risk.authorize(entry, now)["reasons"]


@pytest.mark.parametrize("change,reason", [({"amount": 0.003}, "order size limit"),
    ({"rate": 49000}, "price deviation limit"), ({"amount": 1e308}, "order size limit")])
def test_order_limits(risk, snapshot, entry, now, change, reason):
    risk.snapshot(snapshot, now)
    assert reason in risk.authorize(changed(entry, **change), now)["reasons"]


def test_spread(risk, snapshot, entry, now):
    snapshot.quotes["BTC/EUR"].bid = 49000
    risk.snapshot(snapshot, now)
    assert "spread limit" in risk.authorize(entry, now)["reasons"]


def test_cash(risk, snapshot, entry, now):
    snapshot.cash = 90
    risk.snapshot(snapshot, now)
    assert "cash buffer" in risk.authorize(entry, now)["reasons"]


def test_planned_risk(risk, snapshot, entry, now):
    snapshot.equity = snapshot.cash = 400
    risk.snapshot(snapshot, now)
    assert "planned risk limit" in risk.authorize(entry, now)["reasons"]


def test_total_exposure(risk, snapshot, entry, now):
    snapshot.exposures = {"ETH/EUR": 350}
    risk.snapshot(snapshot, now)
    assert "aggregate exposure limit" in risk.authorize(entry, now)["reasons"]


def test_loss_halt_and_baseline(risk, snapshot, entry, now):
    risk.snapshot(snapshot, now)
    snapshot.observed_at = snapshot.engine_at = now + 1
    snapshot.equity = 975
    risk.snapshot(snapshot, now + 1)
    assert not risk.authorize(entry, now + 1)["allowed"]
    with pytest.raises(ValueError):
        risk.resume(now + 1)
    assert risk.store.state()["day_start"] == 1000


def test_restart_retains_halt(tmp_path, snapshot, entry, now):
    url = "sqlite:///" + str(tmp_path / "ledger.sqlite")
    store = Store(url)
    risk = Risk(store, Policy())
    risk.snapshot(snapshot, now)
    risk.halt("operator test", now)
    store.engine.dispose()
    restored = Risk(Store(url), Policy())
    assert not restored.authorize(entry, now)["allowed"]
    assert restored.store.state()["halt"] == "operator test"


def test_reservations_need_reconciliation(risk, snapshot, entry, now):
    risk.snapshot(snapshot, now)
    risk.authorize(entry, now)
    assert len(risk.store.state()["reservations"]) == 1
    snapshot.observed_at = snapshot.engine_at = now + 121
    for quote in snapshot.quotes.values():
        quote.observed_at = now + 121
    risk.snapshot(snapshot, now + 121)
    assert not risk.store.state()["reservations"]
    assert risk.authorize(changed(entry, request_id="b" * 32), now + 121)["allowed"]


def test_position_replaces_reservation(risk, snapshot, entry, now):
    risk.snapshot(snapshot, now)
    risk.authorize(entry, now)
    snapshot.observed_at = snapshot.engine_at = now + 1
    snapshot.exposures = {"BTC/EUR": 100}
    risk.snapshot(snapshot, now + 1)
    assert not risk.store.state()["reservations"]
    assert not risk.authorize(changed(entry, request_id="b" * 32), now + 1)["allowed"]


@pytest.mark.parametrize("rating,allowed", [("Buy", True), ("Overweight", True), ("Sell", False),
    ("Hold", False), ("Underweight", False), ("REVIEW", False)])
def test_ai_filter(store, snapshot, entry, now, rating, allowed):
    risk = Risk(store, dataclasses.replace(Policy(), ai_filter=True))
    risk.snapshot(snapshot, now)
    risk.research(Research(pair="BTC/EUR", source_symbol="BTC-USD", started_at=now - 10,
        completed_at=now, rating=rating, summary="Untrusted research data", provider="test", model="fake"), now)
    assert risk.authorize(entry, now)["allowed"] is allowed


def test_missing_ai_report(store, snapshot, entry, now):
    risk = Risk(store, dataclasses.replace(Policy(), ai_filter=True))
    risk.snapshot(snapshot, now)
    assert not risk.authorize(entry, now)["allowed"]


@pytest.mark.parametrize("field,value", [("equity", math.nan), ("dry_run", False), ("exposures", {"BTC/EUR": math.inf})])
def test_bad_snapshot(snapshot, field, value):
    with pytest.raises(ValidationError):
        Snapshot.model_validate({**snapshot.model_dump(), field: value})


def test_crossed_quote():
    with pytest.raises(ValidationError):
        Quote(bid=11, ask=10, observed_at=100)
