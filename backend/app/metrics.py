import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
from time import perf_counter

from fastapi import FastAPI, Request, Response
import psutil
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest


HTTP_REQUESTS = Counter(
    "parkrock_http_requests_total",
    "Количество HTTP-запросов к API.",
    ("method", "route", "status"),
)
HTTP_REQUEST_DURATION = Histogram(
    "parkrock_http_request_duration_seconds",
    "Длительность HTTP-запросов к API.",
    ("method", "route"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
FASTAPI_APP_NAME = "parkrock-backend"
FASTAPI_APP_INFO = Gauge(
    "fastapi_app_info",
    "Информация о FastAPI-приложении для стандартных Grafana-дашбордов.",
    ("app_name",),
)
FASTAPI_REQUESTS = Counter(
    "fastapi_requests_total",
    "Количество HTTP-запросов к FastAPI-приложению.",
    ("app_name", "method", "path"),
)
FASTAPI_RESPONSES = Counter(
    "fastapi_responses_total",
    "Количество HTTP-ответов FastAPI-приложения.",
    ("app_name", "method", "path", "status_code"),
)
FASTAPI_REQUEST_DURATION = Histogram(
    "fastapi_requests_duration_seconds",
    "Длительность HTTP-запросов к FastAPI-приложению.",
    ("app_name", "path"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
FASTAPI_EXCEPTIONS = Counter(
    "fastapi_exceptions_total",
    "Количество необработанных исключений FastAPI-приложения.",
    ("app_name", "path", "exception_type"),
)
FASTAPI_REQUESTS_IN_PROGRESS = Gauge(
    "fastapi_requests_in_progress",
    "Количество HTTP-запросов, обрабатываемых FastAPI-приложением.",
    ("app_name", "path"),
)
PROCESS = psutil.Process()
PROCESS_MEMORY = Gauge(
    "parkrock_process_resident_memory_bytes",
    "Объём физической памяти процесса backend.",
)
PROCESS_CPU = Gauge(
    "parkrock_process_cpu_seconds_total",
    "Процессорное время процесса backend.",
)
PROCESS_MEMORY.set_function(lambda: PROCESS.memory_info().rss)
PROCESS_CPU.set_function(lambda: sum(PROCESS.cpu_times()[:2]))
FASTAPI_APP_INFO.labels(FASTAPI_APP_NAME).set(1)


def _access_logger() -> logging.Logger:
    logger = logging.getLogger("parkrock.access")
    log_path = os.getenv("PARKROCK_LOG_FILE")
    if not log_path or logger.handlers:
        return logger

    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(path, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s - "
        "[trace_id=- span_id=- service_name=parkrock-backend] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def setup_metrics(app: FastAPI) -> None:
    access_logger = _access_logger()

    @app.middleware("http")
    async def collect_http_metrics(request: Request, call_next):
        if request.url.path == "/metrics":
            return await call_next(request)

        started_at = perf_counter()
        status_code = 500
        pending_path = "pending"
        FASTAPI_REQUESTS_IN_PROGRESS.labels(FASTAPI_APP_NAME, pending_path).inc()
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception as exc:
            FASTAPI_EXCEPTIONS.labels(FASTAPI_APP_NAME, request.url.path, type(exc).__name__).inc()
            raise
        finally:
            FASTAPI_REQUESTS_IN_PROGRESS.labels(FASTAPI_APP_NAME, pending_path).dec()
            route = request.scope.get("route")
            route_path = getattr(route, "path", "unmatched")
            duration = perf_counter() - started_at
            HTTP_REQUESTS.labels(request.method, route_path, str(status_code)).inc()
            HTTP_REQUEST_DURATION.labels(request.method, route_path).observe(duration)
            FASTAPI_REQUESTS.labels(FASTAPI_APP_NAME, request.method, route_path).inc()
            FASTAPI_RESPONSES.labels(FASTAPI_APP_NAME, request.method, route_path, str(status_code)).inc()
            FASTAPI_REQUEST_DURATION.labels(FASTAPI_APP_NAME, route_path).observe(duration)
            access_logger.info("%s %s %s %.6fs", request.method, route_path, status_code, duration)

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(content=generate_latest(), headers={"Content-Type": CONTENT_TYPE_LATEST})
