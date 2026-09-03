from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.db import engine


LEGACY_TABLES = {
    "admins",
    "age_groups",
    "ascents",
    "competition_sets",
    "events",
    "participants",
    "published_results",
    "routes",
}
INITIAL_REVISION = "0001_initial"


def migrate() -> None:
    config = Config("alembic.ini")
    existing_tables = set(inspect(engine).get_table_names())
    if existing_tables and "alembic_version" not in existing_tables:
        if existing_tables != LEGACY_TABLES:
            unexpected = ", ".join(sorted(existing_tables ^ LEGACY_TABLES))
            raise RuntimeError(
                "Найдена неизвестная схема базы без истории миграций. "
                f"Отличающиеся таблицы: {unexpected or 'нет данных'}"
            )
        command.stamp(config, INITIAL_REVISION)
    command.upgrade(config, "head")


if __name__ == "__main__":
    migrate()
