import asyncio
import logging

from sqlalchemy import select

from app import backup_service
from app.db import SessionLocal
from app.models import Event


logger = logging.getLogger(__name__)
BACKUP_INTERVAL_SECONDS = 60 * 60


def create_hourly_backup() -> None:
    if not backup_service.BACKUP_OPERATION_LOCK.acquire(blocking=False):
        return
    db = SessionLocal()
    try:
        event = db.scalar(select(Event).order_by(Event.starts_on.desc()))
        if not event or not event.qualification_started_at:
            return
        stage_label = {
            "qualification": "Квалификация",
            "final": "Финал",
            "completed": "Завершено",
        }[event.stage.value]
        backup_service.create_backup(
            db,
            source="automatic",
            note=f"Ежечасная автоматическая копия · этап «{stage_label}»",
            context={"event_id": str(event.id), "stage": event.stage.value, "kind": "hourly"},
        )
    except Exception:
        logger.exception("Не удалось создать ежечасную резервную копию")
    finally:
        db.close()
        backup_service.BACKUP_OPERATION_LOCK.release()


async def hourly_backup_loop() -> None:
    while True:
        await asyncio.sleep(BACKUP_INTERVAL_SECONDS)
        await asyncio.to_thread(create_hourly_backup)
