"""Production launcher: isolated multiprocess metrics and supervised API workers."""
import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--workers", type=int, default=int(os.getenv("WEB_CONCURRENCY", "4")))
    parser.add_argument("--forwarded-allow-ips", default=os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1"))
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        parser.error("workers must be 1–4; more workers require reviewing PostgreSQL connection capacity")

    # Must precede importing prometheus_client or any application module.
    with tempfile.TemporaryDirectory(prefix="parkrock-metrics-", dir=os.getenv("PARKROCK_RUNTIME_DIRECTORY")) as directory:
        os.environ["PROMETHEUS_MULTIPROC_DIR"] = str(Path(directory).resolve())
        import psutil
        from prometheus_client import multiprocess

        parent = psutil.Process()
        server = subprocess.Popen([
            sys.executable, "-m", "uvicorn", "app.main:app", "--host", args.host,
            "--port", str(args.port), "--workers", str(args.workers), "--no-access-log",
            "--proxy-headers", f"--forwarded-allow-ips={args.forwarded_allow_ips}",
        ], creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
        shutdown_at = None

        def shutdown(signum, frame):
            nonlocal shutdown_at
            if shutdown_at is None and server.poll() is None:
                shutdown_at = time.monotonic()
                server.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGTERM)

        signals = [signal.SIGINT, signal.SIGTERM]
        if os.name == "nt":
            signals.append(signal.SIGBREAK)
        handlers = {sig: signal.signal(sig, shutdown) for sig in signals}
        previous = set()
        children = []
        try:
            while server.poll() is None:
                children = parent.children(recursive=True)
                current = {p.pid for p in children}
                for pid in previous - current:
                    multiprocess.mark_process_dead(pid, directory)
                previous = current
                if shutdown_at is not None and time.monotonic() - shutdown_at > 25:
                    break
                time.sleep(0.5)
        finally:
            # The parent never opens metric mmap files. All writers must exit
            # before TemporaryDirectory removes them, including on Windows.
            for child in reversed(children):
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
            psutil.wait_procs(children, timeout=5)
            if server.poll() is None:
                server.kill()
            server.wait()
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
        if shutdown_at is None and server.returncode:
            raise SystemExit(server.returncode)


if __name__ == "__main__":
    main()
