"""Durable ledger. PostgreSQL row locks serialize concurrent entry grants."""
import copy
import threading
from contextlib import contextmanager
from sqlalchemy import JSON, Column, Float, Integer, MetaData, String, Table, create_engine, insert, select, update
from sqlalchemy.pool import StaticPool

metadata = MetaData()
control = Table("tina_control", metadata, Column("id", Integer, primary_key=True),
                Column("data", JSON, nullable=False))
events = Table("tina_events", metadata, Column("id", Integer, primary_key=True),
               Column("at", Float, nullable=False), Column("kind", String(32), nullable=False),
               Column("data", JSON, nullable=False))


def initial_state():
    return {"snapshot": None, "halt": None, "reconcile_error": "not yet reconciled",
            "high_water": 0, "day": "", "day_start": 0, "entries": 0,
            "reservations": [], "reports": {}, "last_equity_at": 0}


class Store:
    def __init__(self, url: str):
        kwargs = {"pool_pre_ping": True}
        if url == "sqlite://":
            kwargs.update(poolclass=StaticPool, connect_args={"check_same_thread": False})
        self.engine = create_engine(url, **kwargs)
        self.lock = threading.RLock()
        metadata.create_all(self.engine)
        with self.engine.begin() as conn:
            if conn.execute(select(control.c.id)).first() is None:
                conn.execute(insert(control).values(id=1, data=initial_state()))

    @contextmanager
    def transaction(self):
        with self.lock, self.engine.begin() as conn:
            row = conn.execute(select(control.c.data).where(control.c.id == 1).with_for_update()).one()
            state = copy.deepcopy(row[0])
            yield conn, state
            conn.execute(update(control).where(control.c.id == 1).values(data=state))

    @staticmethod
    def event(conn, kind, data, now):
        conn.execute(insert(events).values(kind=kind, data=data, at=now))

    def state(self):
        with self.lock, self.engine.connect() as conn:
            return copy.deepcopy(conn.execute(select(control.c.data).where(control.c.id == 1)).scalar_one())

    def history(self, kind, limit=100):
        with self.lock, self.engine.connect() as conn:
            rows = conn.execute(select(events).where(events.c.kind == kind)
                                .order_by(events.c.id.desc()).limit(limit)).mappings().all()
            return [dict(r) for r in rows]

    def seen(self, conn, request_id):
        return conn.execute(select(events.c.id).where(
            events.c.kind == "decision", events.c.data["request_id"].as_string() == request_id
        ).limit(1)).first() is not None
