from enum import Enum

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Admin, RolePermission, UserRole


class Permission(str, Enum):
    dashboard_view = "dashboard.view"
    participants_view = "participants.view"
    participants_manage = "participants.manage"
    participants_import = "participants.import"
    clubs_manage = "clubs.manage"
    results_manage = "results.manage"
    sets_manage = "sets.manage"
    routes_manage = "routes.manage"
    settings_manage = "settings.manage"
    users_manage = "users.manage"
    roles_manage = "roles.manage"
    audit_view = "audit.view"
    exports_create = "exports.create"
    final_manage = "final.manage"
    judge_results = "judge.results"


PERMISSION_LABELS = {
    Permission.dashboard_view: "Просмотр панели фестиваля",
    Permission.participants_view: "Просмотр участников",
    Permission.participants_manage: "Прибытие и изменение участников",
    Permission.participants_import: "Импорт участников",
    Permission.clubs_manage: "Редактирование клубов",
    Permission.results_manage: "Изменение результатов квалификации",
    Permission.sets_manage: "Управление сетами",
    Permission.routes_manage: "Управление трассами",
    Permission.settings_manage: "Настройки соревнования",
    Permission.users_manage: "Управление пользователями",
    Permission.roles_manage: "Настройка прав ролей",
    Permission.audit_view: "Просмотр журнала действий",
    Permission.exports_create: "Формирование выгрузок",
    Permission.final_manage: "Управление финалом",
    Permission.judge_results: "Внесение результата на назначенной трассе",
}


STANDARD_PERMISSIONS = {
    UserRole.reception: {
        Permission.dashboard_view, Permission.participants_view,
        Permission.participants_manage, Permission.participants_import,
    },
    UserRole.secretary: {
        Permission.dashboard_view, Permission.participants_view, Permission.participants_manage,
        Permission.participants_import, Permission.results_manage, Permission.sets_manage,
        Permission.routes_manage, Permission.settings_manage, Permission.audit_view, Permission.clubs_manage,
        Permission.exports_create, Permission.final_manage,
    },
    UserRole.chief_judge: {
        Permission.dashboard_view, Permission.participants_view, Permission.participants_manage,
        Permission.participants_import, Permission.results_manage, Permission.sets_manage,
        Permission.routes_manage, Permission.settings_manage, Permission.audit_view, Permission.clubs_manage,
        Permission.exports_create, Permission.final_manage,
    },
    UserRole.administrator: set(Permission),
    UserRole.route_judge: {
        Permission.dashboard_view, Permission.participants_view, Permission.judge_results,
    },
}


def effective_permissions(db: Session, role: UserRole) -> set[Permission]:
    rows = list(db.scalars(select(RolePermission).where(RolePermission.role == role)).all())
    if not rows:
        return set(STANDARD_PERMISSIONS[role])
    known = {item.value: item for item in Permission}
    return {known[row.permission] for row in rows if row.is_allowed and row.permission in known}


def require_permission(permission: Permission):
    from app.deps import get_current_admin

    def dependency(admin: Admin = Depends(get_current_admin), db: Session = Depends(get_db)) -> Admin:
        if permission not in effective_permissions(db, admin.role):
            from app.audit import write_audit
            write_audit(
                db, actor=admin, action="authorization.denied", target_type="permission",
                target_id=permission.value, result="denied",
            )
            db.commit()
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
        return admin

    return dependency
