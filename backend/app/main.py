import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm.exc import StaleDataError

from app.config import settings
from app.audit import write_audit
from app.db import SessionLocal
from app.models import Admin
from app.metrics import setup_metrics
from app.security import decode_access_token
from app.routers import admin, admin_backups, admin_categories, admin_clubs, admin_final, admin_routes, admin_sets, admin_users, applications, auth, judge, public

app = FastAPI(title="ParkRock Hub API", version="0.2.0")
setup_metrics(app)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


VALIDATION_FIELDS = {
    "email": "Почта", "full_name": "ФИО", "password": "Пароль", "role": "Роль",
    "assigned_route_id": "Трасса судьи", "X-Operation-Id": "Идентификатор операции",
}


def validation_detail(errors: list[dict]) -> str:
    messages = []
    for error in errors:
        field = VALIDATION_FIELDS.get(str(error.get("loc", [""])[-1]), str(error.get("loc", [""])[-1]))
        error_type = error.get("type", "")
        if error_type == "missing":
            message = "поле обязательно"
        elif error_type == "string_too_short":
            message = f"минимум {error.get('ctx', {}).get('min_length', 1)} символов"
        elif "email" in error_type or "email" in str(error.get("msg", "")).lower():
            message = "некорректный адрес"
        elif error_type == "enum":
            message = "неизвестная роль"
        else:
            message = "некорректное значение"
        messages.append(f"{field}: {message}")
    return "; ".join(messages)


@app.exception_handler(RequestValidationError)
def request_validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    detail = validation_detail(exc.errors())
    request.state.audit_error_detail = detail
    return JSONResponse(status_code=422, content={"detail": detail})


@app.exception_handler(HTTPException)
def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    request.state.audit_error_detail = detail.get("message", str(detail)) if isinstance(detail, dict) else str(detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": detail}, headers=exc.headers)


@app.middleware("http")
async def audit_failed_admin_commands(request: Request, call_next):
    response = await call_next(request)
    if (
        request.url.path.startswith("/api/v1/admin")
        and request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and response.status_code >= 400
        and response.status_code != 403
    ):
        db = SessionLocal()
        try:
            actor = None
            authorization = request.headers.get("authorization", "")
            if authorization.lower().startswith("bearer "):
                subject = decode_access_token(authorization[7:])
                try:
                    actor = db.get(Admin, uuid.UUID(subject or ""))
                except ValueError:
                    actor = None
            route = request.scope.get("route")
            failure = {"method": request.method, "status": response.status_code}
            if getattr(request.state, "audit_error_detail", ""):
                failure["detail"] = request.state.audit_error_detail
            write_audit(
                db, actor=actor, action="request.failed", target_type="api",
                target_id=getattr(route, "path", request.url.path),
                new_value=failure, result="error",
            )
            db.commit()
        finally:
            db.close()
    return response


@app.exception_handler(StaleDataError)
def stale_data_error_handler(_, __: StaleDataError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"detail": {"code": "edit_conflict", "message": "Данные уже изменены на другом рабочем месте."}},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth.router, prefix="/api/v1")
app.include_router(public.router, prefix="/api/v1")
app.include_router(applications.public_router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(admin_backups.router, prefix="/api/v1")
app.include_router(admin_clubs.router, prefix="/api/v1")
app.include_router(admin_categories.router, prefix="/api/v1")
app.include_router(admin_final.router, prefix="/api/v1")
app.include_router(admin_routes.router, prefix="/api/v1")
app.include_router(admin_sets.router, prefix="/api/v1")
app.include_router(admin_users.router, prefix="/api/v1")
app.include_router(applications.admin_router, prefix="/api/v1")
app.include_router(judge.router, prefix="/api/v1")
