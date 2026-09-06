import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from app import automatic_backups, backup_service
from app.process_lock import ProcessLock


def test_backup_lock_blocks_other_process_and_recovers_after_crash(tmp_path):
    path = tmp_path / "backup.lock"
    script = """
import sys
from pathlib import Path
from app.process_lock import ProcessLock
lock = ProcessLock(lambda: Path(sys.argv[1]))
print(lock.acquire(False), flush=True)
sys.stdin.readline()
"""
    owner = subprocess.Popen([sys.executable, "-c", script, str(path)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert owner.stdout.readline().strip() == "True"
        local = ProcessLock(lambda: path)
        assert not local.acquire(False)
        owner.kill()
        owner.wait(5)
        assert local.acquire(False)
        assert not local.acquire(False)
        local.release()
        assert local.acquire(False)
        local.release()
    finally:
        if owner.poll() is None:
            owner.kill()
            owner.wait(5)
        owner.stdin.close()
        owner.stdout.close()


def test_hourly_backup_success_is_shared_and_failure_can_retry(monkeypatch, tmp_path):
    monkeypatch.setattr(backup_service, "BACKUP_DIRECTORY", tmp_path)
    monkeypatch.setattr(backup_service, "BACKUP_OPERATION_LOCK", ProcessLock(lambda: tmp_path / ".operation.lock"))
    event = SimpleNamespace(id="test-event", qualification_started_at=True, stage=SimpleNamespace(value="qualification"))
    monkeypatch.setattr(automatic_backups, "SessionLocal", lambda: SimpleNamespace(scalar=lambda _: event, close=lambda: None))
    calls = []

    def backup(*args, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError("Simulated dump failure")

    monkeypatch.setattr(backup_service, "create_backup", backup)
    automatic_backups.create_hourly_backup()
    assert not (tmp_path / ".hourly-success").exists()
    automatic_backups.create_hourly_backup()
    automatic_backups.create_hourly_backup()
    assert len(calls) == 2
    os.utime(tmp_path / ".hourly-success", (1, 1))
    automatic_backups.create_hourly_backup()
    assert len(calls) == 3


def test_multiprocess_metrics_merge_and_dead_worker_cleanup(tmp_path):
    env = dict(os.environ, PROMETHEUS_MULTIPROC_DIR=str(tmp_path))
    script = """
import os
from app.metrics import HTTP_REQUESTS, PROCESS_MEMORY, FASTAPI_APP_INFO, FASTAPI_APP_NAME
from app.db import DB_ACTIVE
HTTP_REQUESTS.labels('GET', '/test', '200').inc(7)
PROCESS_MEMORY.set(100)
DB_ACTIVE.set(2)
print(os.getpid())
"""
    pids = [int(subprocess.check_output([sys.executable, "-c", script], env=env, text=True)) for _ in range(2)]
    # Import in this process is deliberately single-process, like the test runner.
    from prometheus_client import CollectorRegistry, generate_latest, multiprocess

    def samples():
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry, path=str(tmp_path))
        return generate_latest(registry).decode()

    before = samples()
    assert 'parkrock_http_requests_total{method="GET",route="/test",status="200"} 14.0' in before
    assert "parkrock_process_resident_memory_bytes 200.0" in before
    assert "parkrock_db_request_sessions 4.0" in before
    for pid in pids:
        multiprocess.mark_process_dead(pid, str(tmp_path))
    after = samples()
    assert 'parkrock_http_requests_total{method="GET",route="/test",status="200"} 14.0' in after
    assert "parkrock_db_request_sessions" not in after
