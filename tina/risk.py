"""Deterministic entry checks. No exchange credentials, order submission, or LLM arithmetic."""
import math
import time
from datetime import datetime, timezone
from tina.models import Entry, Research, Snapshot
from tina.settings import Policy
from tina.store import Store


class Risk:
    def __init__(self, store: Store, policy: Policy):
        self.store, self.policy = store, policy

    def invalidate(self, reason):
        with self.store.transaction() as (conn, state):
            if state["reconcile_error"] != reason:
                self.store.event(conn, "reconcile_error", {"reason": reason}, time.time())
            state["reconcile_error"] = reason

    def snapshot(self, snapshot: Snapshot, now=None):
        now = time.time() if now is None else now
        if not 0 <= now - snapshot.observed_at <= self.policy.snapshot_ttl:
            raise ValueError("stale/future snapshot")
        with self.store.transaction() as (conn, state):
            old = state["snapshot"]
            if old and snapshot.observed_at <= old["observed_at"]:
                raise ValueError("non-monotonic snapshot")
            state.update(snapshot=snapshot.model_dump(), reconcile_error=None)
            day = datetime.fromtimestamp(now, timezone.utc).date().isoformat()
            if state["day"] != day:
                state.update(day=day, day_start=snapshot.equity, entries=0)
            state["high_water"] = max(state["high_water"], snapshot.equity)
            state["reservations"] = [r for r in state["reservations"]
                if r["pair"] not in snapshot.exposures and r["expires_at"] > snapshot.observed_at]
            reason = None
            if snapshot.equity <= state["day_start"] * (1 - self.policy.daily_loss_fraction):
                reason = "daily equity loss limit"
            if snapshot.equity <= state["high_water"] * (1 - self.policy.drawdown_fraction):
                reason = "portfolio drawdown limit"
            if reason and not state["halt"]:
                state["halt"] = reason
                self.store.event(conn, "halt", {"reason": reason}, now)
            if now - state["last_equity_at"] >= 60:
                self.store.event(conn, "equity", {"equity": snapshot.equity}, now)
                state["last_equity_at"] = now

    def research(self, report: Research, now=None):
        now = time.time() if now is None else now
        if report.completed_at > now + 5 or now - report.started_at > self.policy.research_ttl:
            raise ValueError("future/stale research")
        with self.store.transaction() as (conn, state):
            old = state["reports"].get(report.pair)
            if old and old["started_at"] >= report.started_at:
                raise ValueError("non-monotonic research")
            state["reports"][report.pair] = report.model_dump()
            self.store.event(conn, "research", report.model_dump(), now)

    def halt(self, reason: str, now=None):
        with self.store.transaction() as (conn, state):
            state["halt"] = reason
            self.store.event(conn, "halt", {"reason": reason}, time.time() if now is None else now)

    def resume(self, now=None):
        now = time.time() if now is None else now
        with self.store.transaction() as (conn, state):
            s = state["snapshot"]
            if state["reconcile_error"] or not s or not 0 <= now - s["observed_at"] <= self.policy.snapshot_ttl:
                raise ValueError("cannot resume without fresh reconciliation")
            if s["equity"] <= max(state["day_start"] * (1 - self.policy.daily_loss_fraction),
                                  state["high_water"] * (1 - self.policy.drawdown_fraction)):
                raise ValueError("loss limits still breached")
            state["halt"] = None  # Never reset baselines, high-water mark, or entry counter.
            self.store.event(conn, "resume", {}, now)

    def authorize(self, entry: Entry, now=None):
        now = time.time() if now is None else now
        p = self.policy
        with self.store.transaction() as (conn, state):
            reasons = []
            if self.store.seen(conn, entry.request_id):
                return {"allowed": False, "reasons": ["duplicate request"], "request_id": entry.request_id}
            if state["halt"]:
                reasons.append("entries halted: " + state["halt"])
            if state["reconcile_error"]:
                reasons.append("reconciliation unavailable")
            s = state["snapshot"]
            if not s or not 0 <= now - s["observed_at"] <= p.snapshot_ttl:
                reasons.append("missing/stale reconciliation")
            elif not 0 <= now - s["engine_at"] <= p.snapshot_ttl:
                reasons.append("engine heartbeat stale")
            else:
                q = s["quotes"].get(entry.pair)
                if not q or not 0 <= now - q["observed_at"] <= p.quote_ttl:
                    reasons.append("missing/stale quote")
                else:
                    if (q["ask"] - q["bid"]) / q["ask"] > p.max_spread:
                        reasons.append("spread limit")
                    if abs(entry.rate / q["ask"] - 1) > p.max_price_deviation:
                        reasons.append("price deviation limit")
                notional = entry.amount * entry.rate
                pending = state["reservations"]  # Only reconciliation releases reservations.
                reserved = sum(r["notional"] for r in pending)
                exposures = s["exposures"]
                if not math.isfinite(notional) or notional > p.max_order:
                    reasons.append("order size limit")
                if entry.pair in exposures or any(r["pair"] == entry.pair for r in pending):
                    reasons.append("existing/pending position")
                if len(exposures) + len(pending) >= p.max_open:
                    reasons.append("open position limit")
                if notional > s["equity"] * p.max_asset_fraction:
                    reasons.append("asset exposure limit")
                if notional + sum(exposures.values()) + reserved > s["equity"] * p.max_total_fraction:
                    reasons.append("aggregate exposure limit")
                if notional + reserved > s["cash"] * 0.99:
                    reasons.append("cash buffer")
                if notional * (p.stop_fraction + p.cost_buffer) > s["equity"] * p.risk_fraction:
                    reasons.append("planned risk limit")
                if state["entries"] >= p.max_entries_day:
                    reasons.append("daily entry limit")
                if p.ai_filter:
                    report = state["reports"].get(entry.pair)
                    if (not report or not 0 <= now - report["started_at"] <= p.research_ttl
                            or report["rating"] not in ("Buy", "Overweight")):
                        reasons.append("AI filter missing, expired, or not supportive")
            result = {"allowed": not reasons, "reasons": reasons, "request_id": entry.request_id}
            if not reasons:
                state["entries"] += 1
                state["reservations"].append({"pair": entry.pair, "notional": entry.amount * entry.rate,
                    "expires_at": now + p.reservation_ttl, "request_id": entry.request_id})
            self.store.event(conn, "decision", {**entry.model_dump(), **result}, now)
            return result
