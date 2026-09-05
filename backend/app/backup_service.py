import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import settings
from app.models import ApplicationFile, Ascent, Club, Event, FinalCategoryResult, FinalRouteAttempt, Participant


BACKUP_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.dump$")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKUP_DIRECTORY = Path(settings.backup_directory).expanduser().resolve() if settings.backup_directory else PROJECT_ROOT / "backups"
BACKUP_OPERATION_LOCK = threading.Lock()
SET_COLUMNS = (
    "id", "event_id", "name", "scheduled_on", "time_label", "capacity",
    "status", "confirmed_at", "version",
)


class BackupError(RuntimeError):
    pass


def _run(args: list[str], *, env: dict[str, str] | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, cwd=cwd)
    if result.returncode:
        message = (result.stderr or result.stdout or "Команда PostgreSQL завершилась с ошибкой.").strip()
        raise BackupError(message[-1200:])
    return result


def _url_parts(database: str | None = None) -> dict[str, Any]:
    url = make_url(settings.database_url)
    return {
        "dbname": database or url.database,
        "user": url.username,
        "password": url.password,
        "host": url.host or "localhost",
        "port": url.port or 5432,
    }


def _psycopg_connection(database: str):
    return psycopg.connect(**_url_parts(database))


def _docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Running}}", settings.backup_postgres_container],
        capture_output=True, text=True,
    )
    return result.returncode == 0 and result.stdout.strip().lower() == "true"


def _local_tool(name: str) -> str | None:
    return shutil.which(name)


def _tooling_mode() -> str:
    if all(_local_tool(name) for name in ("pg_dump", "pg_restore")):
        return "local"
    if _docker_available():
        return "docker"
    raise BackupError("Не найдены утилиты PostgreSQL. Установите pg_dump/pg_restore или запустите контейнер PostgreSQL.")


def _pg_env() -> dict[str, str]:
    env = os.environ.copy()
    password = _url_parts().get("password")
    if password:
        env["PGPASSWORD"] = str(password)
    return env


def _local_connection_args(database: str) -> list[str]:
    parts = _url_parts(database)
    return ["--host", str(parts["host"]), "--port", str(parts["port"]), "--username", str(parts["user"]), "--dbname", database]


def _with_container_file(path: Path, callback):
    container_path = f"/tmp/parkrock-{uuid.uuid4().hex}.dump"
    try:
        _run(["docker", "cp", str(path), f"{settings.backup_postgres_container}:{container_path}"])
        return callback(container_path)
    finally:
        subprocess.run(["docker", "exec", settings.backup_postgres_container, "rm", "-f", container_path], capture_output=True)


def validate_archive(path: Path) -> None:
    if _tooling_mode() == "local":
        _run([str(_local_tool("pg_restore")), "--list", str(path)])
        return
    _with_container_file(path, lambda container_path: _run([
        "docker", "exec", settings.backup_postgres_container, "pg_restore", "--list", container_path,
    ]))


def _restore_archive(path: Path, database: str) -> None:
    if _tooling_mode() == "local":
        _run([
            str(_local_tool("pg_restore")), *_local_connection_args(database),
            "--exit-on-error", "--no-owner", "--no-privileges", str(path),
        ], env=_pg_env())
        return
    _with_container_file(path, lambda container_path: _run([
        "docker", "exec", settings.backup_postgres_container, "pg_restore",
        "--username", str(_url_parts()["user"]), "--dbname", database,
        "--exit-on-error", "--no-owner", "--no-privileges", container_path,
    ]))


def _create_database(database: str) -> None:
    with _psycopg_connection("postgres") as connection:
        connection.autocommit = True
        connection.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(database)))
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))


def _drop_database(database: str) -> None:
    with _psycopg_connection("postgres") as connection:
        connection.autocommit = True
        connection.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(database)))


def _migrate_database(database: str) -> None:
    url = make_url(settings.database_url).set(database=database).render_as_string(hide_password=False)
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    _run([sys.executable, "-m", "app.migrate"], env=env, cwd=PROJECT_ROOT / "backend")


def _capture_set_state(database: str) -> dict[str, list[tuple[Any, ...]]]:
    columns = sql.SQL(", ").join(map(sql.Identifier, SET_COLUMNS))
    with _psycopg_connection(database) as connection:
        sets = connection.execute(sql.SQL(
            "SELECT {} FROM competition_sets ORDER BY event_id, scheduled_on NULLS LAST, name, id"
        ).format(columns)).fetchall()
        assignments = connection.execute(
            "SELECT id, event_id, start_number, set_id FROM participants ORDER BY id"
        ).fetchall()
    return {"sets": sets, "assignments": assignments}


def _apply_set_state(database: str, state: dict[str, list[tuple[Any, ...]]]) -> None:
    set_rows = state["sets"]
    if not set_rows:
        return
    event_ids = sorted({row[1] for row in set_rows}, key=str)
    sets_by_event = {
        event_id: [row for row in set_rows if row[1] == event_id]
        for event_id in event_ids
    }
    assignments = state["assignments"]
    columns = sql.SQL(", ").join(map(sql.Identifier, SET_COLUMNS))
    placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in SET_COLUMNS)
    updates = sql.SQL(", ").join(
        sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(column), sql.Identifier(column))
        for column in SET_COLUMNS[1:]
    )
    insert_set = sql.SQL(
        "INSERT INTO competition_sets ({}) VALUES ({}) ON CONFLICT (id) DO UPDATE SET {}"
    ).format(columns, placeholders, updates)
    with _psycopg_connection(database) as connection:
        restored_event_ids = {row[0] for row in connection.execute(
            "SELECT id FROM events WHERE id = ANY(%s::uuid[])", (event_ids,),
        ).fetchall()}
        missing_event_ids = set(event_ids) - restored_event_ids
        if missing_event_ids:
            raise BackupError("В резервной копии отсутствует фестиваль, для которого настроены текущие сеты.")
        with connection.cursor() as cursor:
            cursor.executemany(insert_set, set_rows)
        preserved_set_ids = {row[0] for row in set_rows}
        matching_assignments = [
            (set_id, event_id, start_number)
            for _, event_id, start_number, set_id in assignments
            if set_id in preserved_set_ids
        ]
        if matching_assignments:
            with connection.cursor() as cursor:
                cursor.executemany(
                    "UPDATE participants SET set_id = %s WHERE event_id = %s AND start_number = %s",
                    matching_assignments,
                )
        for event_id, event_sets in sets_by_event.items():
            set_ids = [row[0] for row in event_sets]
            fallback_set_id = set_ids[0]
            connection.execute(
                "UPDATE participants SET set_id = %s WHERE event_id = %s AND NOT (set_id = ANY(%s::uuid[]))",
                (fallback_set_id, event_id, set_ids),
            )
            connection.execute(
                "DELETE FROM competition_sets WHERE event_id = %s AND NOT (id = ANY(%s::uuid[]))",
                (event_id, set_ids),
            )


def _database_summary(database: str) -> dict[str, Any]:
    table_names = ["events", "participants", "clubs", "applications", "ascents", "final_category_results", "final_route_attempts", "audit_logs"]
    summary: dict[str, Any] = {"counts": {}}
    with _psycopg_connection(database) as connection:
        existing = {row[0] for row in connection.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        ).fetchall()}
        if not existing:
            raise BackupError("В восстановленной базе не найдены таблицы приложения.")
        for table in table_names:
            if table in existing:
                summary["counts"][table] = connection.execute(
                    sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
                ).fetchone()[0]
        if "events" in existing:
            row = connection.execute(
                "SELECT title, location, starts_on, stage::text FROM events ORDER BY starts_on DESC LIMIT 1"
            ).fetchone()
            if row:
                summary["event"] = {"title": row[0], "location": row[1], "starts_on": str(row[2]), "stage": row[3]}
    return summary


def current_summary(db: Session) -> dict[str, Any]:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()).limit(1))
    return {
        "event": ({"title": event.title, "location": event.location, "starts_on": str(event.starts_on), "stage": event.stage.value} if event else None),
        "counts": {
            "events": db.scalar(select(func.count(Event.id))) or 0,
            "participants": db.scalar(select(func.count(Participant.id))) or 0,
            "clubs": db.scalar(select(func.count(Club.id))) or 0,
            "applications": db.scalar(select(func.count(ApplicationFile.id))) or 0,
            "ascents": db.scalar(select(func.count(Ascent.id))) or 0,
            "final_category_results": db.scalar(select(func.count(FinalCategoryResult.id))) or 0,
            "final_route_attempts": db.scalar(select(func.count(FinalRouteAttempt.id))) or 0,
        },
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _metadata_path(path: Path) -> Path:
    return path.with_suffix(".json")


def _write_metadata(path: Path, metadata: dict[str, Any]) -> None:
    target = _metadata_path(path)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(metadata, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    temporary.replace(target)


def _read_metadata(path: Path) -> dict[str, Any]:
    try:
        return json.loads(_metadata_path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def resolve_backup(filename: str) -> Path:
    if not BACKUP_NAME.fullmatch(filename):
        raise BackupError("Некорректное имя резервной копии.")
    BACKUP_DIRECTORY.mkdir(parents=True, exist_ok=True)
    path = (BACKUP_DIRECTORY / filename).resolve()
    if path.parent != BACKUP_DIRECTORY.resolve() or not path.is_file():
        raise BackupError("Резервная копия не найдена.")
    return path


def backup_item(path: Path, current: dict[str, Any] | None = None) -> dict[str, Any]:
    stat = path.stat()
    metadata = _read_metadata(path)
    created_at = metadata.get("created_at") or datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
    summary = metadata.get("summary")
    source = metadata.get("source", "automatic" if "-automatic.dump" in path.name else "legacy")
    if source == "factory-zero" and summary and summary.get("event"):
        summary = {**summary, "event": {**summary["event"], "stage": "preparation"}}
    differences = None
    if current and summary:
        differences = {}
        for key, current_value in current.get("counts", {}).items():
            backup_value = summary.get("counts", {}).get(key)
            if backup_value is not None:
                differences[key] = int(backup_value) - int(current_value)
    return {
        "filename": path.name,
        "created_at": created_at,
        "size_bytes": stat.st_size,
        "source": source,
        "verified_at": metadata.get("verified_at"),
        "checksum_sha256": metadata.get("checksum_sha256"),
        "summary": summary,
        "differences": differences,
        "note": metadata.get("note", ""),
    }


def list_backups(db: Session) -> dict[str, Any]:
    BACKUP_DIRECTORY.mkdir(parents=True, exist_ok=True)
    current = current_summary(db)
    items = [backup_item(path, current) for path in BACKUP_DIRECTORY.glob("*.dump") if BACKUP_NAME.fullmatch(path.name)]
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return {"items": items, "current": current, "directory": str(BACKUP_DIRECTORY)}


def create_backup(
    db: Session, *, source: str = "manual", note: str = "",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    BACKUP_DIRECTORY.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc)
    filename = f"climbhub-{timestamp.strftime('%Y%m%d-%H%M%S')}-{source}.dump"
    path = BACKUP_DIRECTORY / filename
    mode = _tooling_mode()
    try:
        if mode == "local":
            _run([
                str(_local_tool("pg_dump")), *_local_connection_args(str(_url_parts()["dbname"])),
                "--format", "custom", "--file", str(path),
            ], env=_pg_env())
        else:
            container_path = f"/tmp/{filename}"
            try:
                _run([
                    "docker", "exec", settings.backup_postgres_container, "pg_dump",
                    "--username", str(_url_parts()["user"]), "--dbname", str(_url_parts()["dbname"]),
                    "--format", "custom", "--file", container_path,
                ])
                _run(["docker", "cp", f"{settings.backup_postgres_container}:{container_path}", str(path)])
            finally:
                subprocess.run(["docker", "exec", settings.backup_postgres_container, "rm", "-f", container_path], capture_output=True)
        validate_archive(path)
        if not path.exists() or path.stat().st_size == 0:
            raise BackupError("Создан пустой файл резервной копии.")
        restored_summary = _restore_and_inspect(path)
        metadata = {
            "created_at": timestamp.isoformat(), "source": source, "note": note,
            "verified_at": timestamp.isoformat(), "checksum_sha256": _sha256(path),
            "summary": restored_summary,
        }
        if context:
            metadata["context"] = context
        _write_metadata(path, metadata)
        return backup_item(path, metadata["summary"])
    except Exception:
        path.unlink(missing_ok=True)
        _metadata_path(path).unlink(missing_ok=True)
        raise


def _restore_and_inspect(path: Path) -> dict[str, Any]:
    validate_archive(path)
    temp_database = f"climbhub_verify_{uuid.uuid4().hex[:12]}"
    try:
        _create_database(temp_database)
        _restore_archive(path, temp_database)
        _migrate_database(temp_database)
        return _database_summary(temp_database)
    finally:
        _drop_database(temp_database)


def verify_backup(path: Path, current: dict[str, Any] | None = None) -> dict[str, Any]:
    summary = _restore_and_inspect(path)
    metadata = _read_metadata(path)
    metadata.update({
        "created_at": metadata.get("created_at") or datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        "source": metadata.get("source", "automatic" if "-automatic.dump" in path.name else "legacy"),
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "checksum_sha256": _sha256(path),
        "summary": summary,
    })
    _write_metadata(path, metadata)
    return backup_item(path, current)


def delete_backup(path: Path) -> None:
    path.unlink()
    _metadata_path(path).unlink(missing_ok=True)


def restore_working_database(
    path: Path, db: Session, *, create_safety: bool = True, safety_note: str | None = None,
) -> dict[str, Any]:
    checked = verify_backup(path, current_summary(db))
    safety = create_backup(
        db, source="pre-restore", note=safety_note or f"Автоматически перед восстановлением {path.name}",
    ) if create_safety else None
    target_database = str(_url_parts()["dbname"])
    set_state = _capture_set_state(target_database)
    replacement_database = f"climbhub_restore_{uuid.uuid4().hex[:12]}"
    rollback_database = f"climbhub_rollback_{uuid.uuid4().hex[:12]}"
    from app.db import engine
    _create_database(replacement_database)
    try:
        _restore_archive(path, replacement_database)
        _migrate_database(replacement_database)
        _database_summary(replacement_database)
        _apply_set_state(replacement_database, set_state)
        db.close()
        engine.dispose()
        with _psycopg_connection("postgres") as connection:
            connection.autocommit = True
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname IN (%s, %s) AND pid <> pg_backend_pid()",
                (target_database, replacement_database),
            )
            connection.execute(sql.SQL("ALTER DATABASE {} RENAME TO {}").format(
                sql.Identifier(target_database), sql.Identifier(rollback_database),
            ))
            try:
                connection.execute(sql.SQL("ALTER DATABASE {} RENAME TO {}").format(
                    sql.Identifier(replacement_database), sql.Identifier(target_database),
                ))
            except Exception:
                connection.execute(sql.SQL("ALTER DATABASE {} RENAME TO {}").format(
                    sql.Identifier(rollback_database), sql.Identifier(target_database),
                ))
                raise
            connection.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(rollback_database)))
    except Exception:
        try:
            _drop_database(replacement_database)
        except Exception:
            pass
        raise
    finally:
        engine.dispose()
    return {"status": "restored", "restored": checked, "safety_backup": safety}


def find_stage_checkpoint(event_id: str, target_stage: str) -> Path:
    BACKUP_DIRECTORY.mkdir(parents=True, exist_ok=True)
    matches: list[tuple[str, Path]] = []
    for path in BACKUP_DIRECTORY.glob("*.dump"):
        if not BACKUP_NAME.fullmatch(path.name):
            continue
        metadata = _read_metadata(path)
        context = metadata.get("context") or {}
        summary = metadata.get("summary") or {}
        event_summary = summary.get("event") or {}
        if (
            context.get("event_id") == event_id
            and context.get("kind") == "stage-transition"
            and event_summary.get("stage") == target_stage
        ):
            matches.append((metadata.get("created_at", ""), path))
    if not matches:
        raise BackupError(f"Не найдена резервная копия этапа «{target_stage}».")
    return max(matches, key=lambda item: item[0])[1]
