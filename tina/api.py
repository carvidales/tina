"""Authenticated control plane: only the engine role can request entry grants."""
import asyncio
import csv
import hmac
import io
import logging
import time
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from tina.collector import collect
from tina.models import Entry, Research
from tina.risk import Risk
from tina.settings import Settings
from tina.store import Store

log = logging.getLogger(__name__)


class HaltRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=200)


def create_app(settings: Settings, store=None, collecting=True):
    store = store or Store(settings.database_url)
    risk = Risk(store, settings.policy)

    async def poll():
        while True:
            try:
                snapshot = await collect(settings)
                await asyncio.to_thread(risk.snapshot, snapshot)
            except Exception as exc:
                log.warning("Reconciliation unavailable (%s); entry approval disabled", type(exc).__name__)
                try:
                    await asyncio.to_thread(risk.invalidate, type(exc).__name__)
                except Exception:
                    log.error("Ledger unavailable; authorization will fail closed")
            await asyncio.sleep(settings.poll_seconds)

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(poll()) if collecting else None
        yield
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="TINA", version="0.1.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.risk, app.state.store = risk, store

    def require(*tokens):
        def check(authorization: str = Header(default="")):
            supplied = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
            if not supplied or not supplied.isascii() or len(supplied) > 256 or not any(hmac.compare_digest(supplied, token) for token in tokens):
                raise HTTPException(401, "invalid credentials")
        return check

    read = require(settings.read_token, settings.admin_token)
    engine = require(settings.engine_token)
    admin = require(settings.admin_token)
    research = require(settings.research_token)

    @app.get("/healthz")
    def health():
        return {"alive": True, "mode": "paper-only"}

    @app.get("/v1/status", dependencies=[Depends(read)])
    def status():
        state = store.state()
        snapshot = state["snapshot"]
        fresh = bool(snapshot and 0 <= time.time() - snapshot["observed_at"] <= settings.policy.snapshot_ttl
                     and 0 <= time.time() - snapshot["engine_at"] <= settings.policy.snapshot_ttl)
        return {"mode": "paper-only", "ready": fresh and state["halt"] is None and state["reconcile_error"] is None,
                "halt": state["halt"], "reconcile_error": state["reconcile_error"], "snapshot": snapshot,
                "entries_today": state["entries"], "ai_policy": "filter" if settings.policy.ai_filter else "shadow",
                "reservations": state["reservations"], "high_water": state["high_water"], "day_start": state["day_start"]}

    @app.post("/v1/entries/authorize", dependencies=[Depends(engine)])
    def authorize(entry: Entry):
        try:
            return risk.authorize(entry)
        except Exception:
            log.exception("Entry check failed; no approval issued")
            raise HTTPException(503, "risk check unavailable") from None

    @app.post("/v1/halt", dependencies=[Depends(admin)])
    def halt(body: HaltRequest):
        risk.halt(body.reason)
        return {"halted": True, "scope": "new entries only; pending orders and positions remain"}

    @app.post("/v1/resume", dependencies=[Depends(admin)])
    def resume():
        try:
            risk.resume()
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        return {"halted": False}

    @app.post("/v1/research", dependencies=[Depends(research)])
    def save_research(report: Research):
        try:
            risk.research(report)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        return {"saved": True, "execution_permission": False}

    @app.get("/v1/research", dependencies=[Depends(read)])
    def reports():
        return store.state()["reports"]

    @app.get("/v1/decisions", dependencies=[Depends(read)])
    def decisions(limit: int = Query(50, ge=1, le=100)):
        return store.history("decision", limit)

    @app.get("/v1/equity.csv", dependencies=[Depends(read)], response_class=PlainTextResponse)
    def equity():
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["timestamp", "equity"])
        for row in reversed(store.history("equity", 200000)):
            writer.writerow([datetime.fromtimestamp(row["at"], timezone.utc).isoformat(), row["data"]["equity"]])
        return output.getvalue()

    return app


def factory():
    return create_app(Settings.from_env())
