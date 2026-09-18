"""One atomic, versioned public projection shared by every viewer and worker."""
import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session, defer

from app.db import engine
from app.models import AgeGroup, Event, EventStage, PublicPublication, Route
from app.services import final_group_participates

logger = logging.getLogger(__name__)
PUBLICATION_LOCK = 731924061


def public_event(db: Session) -> Event:
    event = db.scalar(select(Event).where(Event.is_public.is_(True)).order_by(Event.starts_on.desc(), Event.id))
    if event is None:
        raise HTTPException(404, "Нет опубликованного фестиваля")
    return event


def read_publication(db: Session, event: Event, version: uuid.UUID | None = None, *, path: tuple[str, ...] = ()):
    payload = PublicPublication.payload
    for key in path:
        payload = payload[key]
    query = select(PublicPublication.publication_id, PublicPublication.published_at, PublicPublication.source_stage,
                   payload.label("payload")).where(PublicPublication.event_id == event.id)
    if version is not None:
        query = query.where(PublicPublication.publication_id == version)
    publication = db.execute(query.order_by(PublicPublication.version.desc()).limit(1)).first()
    if publication is None or publication.source_stage != event.stage.value:
        if version is not None:
            raise HTTPException(409, "Версия результатов обновилась. Обновите таблицу.")
        raise HTTPException(503, "Результаты готовятся к публикации", headers={"Retry-After": "1"})
    return publication


def published_response(publication: PublicPublication, value: dict) -> dict:
    return {**value, "publication_version": str(publication.publication_id), "published_at": publication.published_at}


def build_publication(db: Session, event: Event) -> dict:
    from app.routers import public

    result = public.build_results(db=db)
    finals = {}
    if event.stage in (EventStage.final, EventStage.completed):
        for group in db.scalars(select(AgeGroup).where(AgeGroup.event_id == event.id)):
            if final_group_participates(group):
                # Only categories present in the published final roster have a snapshot.
                if group.name in result.final_groups:
                    finals[group.name] = public.build_final_results(group.name, db)
    routes = {route.id: route for route in db.scalars(select(Route).where(
        Route.event_id == event.id, Route.is_active.is_(True)))}
    participants = {str(row["participant"].id): public.build_participant_detail(
        row["participant"].id, db, row=row, routes=routes)
        for row in public.live_result_rows(db, event)}
    return jsonable_encoder({
        "results": result,
        "final_results": finals,
        "absolute_results": {stage: public.build_absolute_results(stage, db)
                             for stage in ("qualification", "final", "overall")},
        "team_results": {stage: public.build_public_team_results(stage, db)
                         for stage in ("qualification", "final")},
        "participants": participants,
    })


def invalidate_publications(db: Session, event: Event) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": PUBLICATION_LOCK})
    db.execute(delete(PublicPublication).where(PublicPublication.event_id == event.id))


def refresh_publications(*, force: bool = False) -> bool:
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        locked = False
        try:
            # Take the session lock BEFORE opening the read snapshot, so a
            # previous publisher's commit cannot be hidden by an older snapshot.
            locked = bool(connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": PUBLICATION_LOCK}))
            connection.commit()
            if not locked:
                return False
            with Session(bind=connection) as db, db.begin():
                event = db.scalar(select(Event).where(Event.is_public.is_(True)).order_by(Event.starts_on.desc(), Event.id))
                if event is None:
                    return False
                latest = db.scalar(select(PublicPublication).options(defer(PublicPublication.payload)).where(PublicPublication.event_id == event.id)
                                   .order_by(PublicPublication.version.desc()).limit(1))
                now = datetime.now(timezone.utc)
                interval = event.final_refresh_seconds if event.stage in (EventStage.final, EventStage.completed) else event.qualification_refresh_seconds
                if not force and latest and latest.source_stage == event.stage.value and (now - latest.published_at).total_seconds() < interval:
                    return False
                payload = build_publication(db, event)
                version = latest.version + 1 if latest else 1
                db.add(PublicPublication(event_id=event.id, version=version, source_stage=event.stage.value,
                                        published_at=datetime.now(timezone.utc), payload=payload))
                # Keep recent versions for multi-request screens, plus the last two on quiet events.
                db.execute(delete(PublicPublication).where(PublicPublication.event_id == event.id,
                                                           PublicPublication.version < version - 1,
                                                           PublicPublication.published_at < now - timedelta(seconds=60)))
                return True
        finally:
            if locked:
                try:
                    connection.rollback()
                    connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": PUBLICATION_LOCK})
                    connection.commit()
                except Exception:
                    # Never return a session holding a lock to the connection pool.
                    connection.invalidate()
                    raise


async def publication_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(refresh_publications)
        except Exception:
            logger.exception("Public results publication failed; retaining the last successful version")
        await asyncio.sleep(1)
