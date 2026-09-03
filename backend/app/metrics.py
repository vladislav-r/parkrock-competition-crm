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


def setup_metrics(app: FastAPI) -> None:
    @app.middleware("http")
    async def collect_http_metrics(request: Request, call_next):
        if request.url.path == "/metrics":
            return await call_next(request)

        started_at = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            route_path = getattr(route, "path", "unmatched")
            HTTP_REQUESTS.labels(request.method, route_path, str(status_code)).inc()
            HTTP_REQUEST_DURATION.labels(request.method, route_path).observe(perf_counter() - started_at)

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(content=generate_latest(), headers={"Content-Type": CONTENT_TYPE_LATEST})
