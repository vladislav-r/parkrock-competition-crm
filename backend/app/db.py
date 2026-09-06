from collections.abc import AsyncGenerator
import os

import anyio
from anyio.lowlevel import RunVar
from fastapi import HTTPException
from prometheus_client import Gauge
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Admission must cover dependencies AND session cleanup. A response middleware
# releases its slot too early and cannot prevent thread/pool starvation.
# The default pool has 15 connections; reserve three for audit/backup work.
REQUEST_SESSION_LIMIT = 12
_session_slots: RunVar[anyio.CapacityLimiter] = RunVar("parkrock_db_session_slots")
DB_WAITING = Gauge("parkrock_db_requests_waiting", "Requests waiting for a database session slot", multiprocess_mode="livesum")
DB_ACTIVE = Gauge("parkrock_db_request_sessions", "Admitted request database sessions", multiprocess_mode="livesum")
DB_CHECKED_OUT = Gauge("parkrock_db_connections_checked_out", "Checked out SQLAlchemy connections", multiprocess_mode="livesum")
if not os.getenv("PROMETHEUS_MULTIPROC_DIR"):
    DB_CHECKED_OUT.set_function(engine.pool.checkedout)


async def get_db() -> AsyncGenerator[Session, None]:
    try:
        slots = _session_slots.get()
    except LookupError:
        slots = anyio.CapacityLimiter(REQUEST_SESSION_LIMIT)
        _session_slots.set(slots)
    DB_WAITING.inc()
    try:
        with anyio.fail_after(5):
            await slots.acquire()
    except TimeoutError:
        raise HTTPException(status_code=503, detail="Сервер занят. Повторите запрос позже.", headers={"Retry-After": "1"})
    finally:
        DB_WAITING.dec()
    DB_ACTIVE.inc()
    try:
        db = SessionLocal()
        try:
            yield db
        finally:
            # Never let cancellation or the shared AnyIO worker limiter prevent
            # returning a connection. The slot stays held until rollback/close.
            with anyio.CancelScope(shield=True):
                await anyio.to_thread.run_sync(db.close, limiter=anyio.CapacityLimiter(1))
    finally:
        DB_ACTIVE.dec()
        slots.release()
