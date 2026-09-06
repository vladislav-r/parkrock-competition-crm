import asyncio
import gzip
import json
from contextlib import asynccontextmanager
from datetime import date
from time import sleep

import httpx
from fastapi import Depends, FastAPI
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import sessionmaker

from app import db as database
from app.models import Ascent, Event, Participant, Route
from app.routers.admin import participant_read, participants


def test_session_admission_prevents_small_pool_starvation(monkeypatch):
    small = create_engine(database.engine.url, pool_size=2, max_overflow=0, pool_timeout=0.1)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=small))
    monkeypatch.setattr(database, "REQUEST_SESSION_LIMIT", 1)
    app = FastAPI()

    def authenticate(db=Depends(database.get_db)):
        db.execute(text("select 1"))
        sleep(0.01)

    @app.get("/business", dependencies=[Depends(authenticate)])
    def business(db=Depends(database.get_db)):
        return {"value": db.scalar(text("select 42"))}

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            replies = await asyncio.wait_for(asyncio.gather(*[client.get("/business") for _ in range(80)]), 8)
            assert all(r.status_code == 200 and r.json() == {"value": 42} for r in replies)
        assert small.pool.checkedout() == 0

    try:
        asyncio.run(run())
    finally:
        small.dispose()


def test_cancelled_session_waiter_and_handler_release_resources(monkeypatch):
    monkeypatch.setattr(database, "REQUEST_SESSION_LIMIT", 1)

    async def run():
        context = asynccontextmanager(database.get_db)
        entered = asyncio.Event()
        async with context() as first:
            first.execute(text("select 1"))

            async def waiting():
                entered.set()
                async with context():
                    raise AssertionError("The occupied slot must not admit this waiter")

            task = asyncio.create_task(waiting())
            await entered.wait()
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        try:
            async with context() as second:
                second.execute(text("select 1"))
                raise ValueError("handler failed")
        except ValueError:
            pass
        assert database._session_slots.get().borrowed_tokens == 0
        assert database.engine.pool.checkedout() == 0

    asyncio.run(run())


def test_batched_participant_response_matches_individual_reads(client, festival):
    with database.SessionLocal() as db:
        from app.models import Club
        club = db.scalar(select(Club))
        for i in range(30):
            db.add(Participant(event_id=festival["event_id"], club_id=club.id,
                set_id=festival["first_set_id"], start_number=i+1, surname=f"Batch{i}", name="Test",
                birth_date=date(2000, 1, 1), sex="male", club=club.name))
        db.commit()
        event_row = db.get(Event, festival["event_id"])
        routes = list(db.scalars(select(Route).where(Route.event_id == event_row.id).order_by(Route.sort_order)))
        items = list(db.scalars(select(Participant).order_by(Participant.start_number)))
        db.add(Ascent(participant_id=items[0].id, route_id=routes[0].id, is_completed=True))
        db.commit()
        expected = [participant_read(db, p, event_row, routes).model_dump() for p in items]

    calls = []
    def count(*args): calls.append(1)
    event.listen(database.engine, "before_cursor_execute", count)
    try:
        with database.SessionLocal() as db:
            actual = [p.model_dump() for p in participants(db=db)]
    finally:
        event.remove(database.engine, "before_cursor_execute", count)
    assert actual == expected
    assert len(calls) == 5
    from app.routers.admin_categories import read_categories
    from app.routers.public import results
    calls.clear()
    event.listen(database.engine, "before_cursor_execute", count)
    try:
        with database.SessionLocal() as db:
            categories = read_categories(db, db.get(Event, festival["event_id"]))
    finally:
        event.remove(database.engine, "before_cursor_execute", count)
    assert sum(item.participant_count for item in categories.categories) == 30
    assert len(calls) == 3
    calls.clear()
    event.listen(database.engine, "before_cursor_execute", count)
    try:
        with database.SessionLocal() as db:
            public = results(db=db)
    finally:
        event.remove(database.engine, "before_cursor_execute", count)
    assert sum(item.participant_count for item in public.sets) == 30
    assert len(calls) == 9
    plain = client.get("/api/v1/public/results", headers={"Accept-Encoding": "identity"})
    with client.stream("GET", "/api/v1/public/results", headers={"Accept-Encoding": "gzip"}) as compressed:
        assert compressed.headers["content-encoding"] == "gzip"
        wire = b"".join(compressed.iter_raw())
    assert json.loads(gzip.decompress(wire)) == plain.json()
    assert len(wire) < len(plain.content) / 2
