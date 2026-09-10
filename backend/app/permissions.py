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
    participants_edit = "participants.edit"
    participants_merge = "participants.merge"
    participants_import = "participants.import"
    clubs_manage = "clubs.manage"
    clubs_merge = "clubs.merge"
    backups_manage = "backups.manage"
    competition_reset = "competition.reset"
    demo_manage = "demo.manage"
    categories_manage = "categories.manage"
    publication_manage = "publication.manage"
    export_settings_manage = "export_settings.manage"
    judge_conflicts_resolve = "judge_conflicts.resolve"
    results_manage = "results.manage"
    sets_manage = "sets.manage"
    routes_manage = "routes.manage"
    users_manage = "users.manage"
    roles_manage = "roles.manage"
    audit_view = "audit.view"
    exports_create = "exports.create"
    final_manage = "final.manage"
    judge_results = "judge.results"


PERMISSION_LABELS = {
    Permission.dashboard_view: "Просмотр панели фестиваля",
    Permission.participants_view: "Просмотр участников",
    Permission.participants_edit: "Редактирование данных участника на подготовке",
    Permission.participants_merge: "Объединение участников на подготовке",
    Permission.participants_manage: "Участники, прибытие, оплата и мерч",
    Permission.participants_import: "Заявки и импорт участников",
    Permission.clubs_manage: "Редактирование клубов",
    Permission.backups_manage: "Резервные копии и восстановление базы",
    Permission.competition_reset: "Сброс данных соревнования",
    Permission.demo_manage: "Демо-данные и массовая очистка участников",
    Permission.clubs_merge: "Объединение клубов",
    Permission.categories_manage: "Настройка возрастных категорий и медалей",
    Permission.publication_manage: "Настройка публичных результатов",
    Permission.export_settings_manage: "Настройка реквизитов выгрузок",
    Permission.judge_conflicts_resolve: "Разрешение конфликтов судейских результатов",
    Permission.results_manage: "Изменение результатов квалификации",
    Permission.sets_manage: "Управление сетами",
    Permission.routes_manage: "Управление трассами",
    Permission.users_manage: "Управление пользователями",
    Permission.roles_manage: "Настройка прав ролей",
    Permission.audit_view: "Просмотр журнала действий",
    Permission.exports_create: "Формирование выгрузок",
    Permission.final_manage: "Квалификация и финал: этапы, подтверждения и результаты финала",
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
        Permission.routes_manage, Permission.categories_manage, Permission.publication_manage, Permission.export_settings_manage, Permission.audit_view, Permission.clubs_manage,
        Permission.exports_create, Permission.final_manage,
    },
    UserRole.chief_judge: {
        Permission.dashboard_view, Permission.participants_view, Permission.participants_manage,
        Permission.participants_import, Permission.results_manage, Permission.sets_manage,
        Permission.routes_manage, Permission.categories_manage, Permission.publication_manage, Permission.export_settings_manage, Permission.audit_view, Permission.clubs_manage,
        Permission.exports_create, Permission.final_manage,
    },
    UserRole.administrator: set(Permission),
    UserRole.route_judge: {
        Permission.dashboard_view, Permission.participants_view, Permission.judge_results,
    },
}


# New granular rights inherit their former gate until the role is explicitly saved.
# Existing denials remain denials; saving the matrix stores every right explicitly.
PERMISSION_PARENTS = {
    Permission.participants_edit: "participants.manage",
    Permission.participants_merge: "participants.manage",
    Permission.clubs_merge: "clubs.manage",
    Permission.categories_manage: "settings.manage",
    Permission.publication_manage: "settings.manage",
    Permission.export_settings_manage: "settings.manage",
    Permission.judge_conflicts_resolve: "final.manage",
}
DEFAULT_PERMISSION_ROLES = {
    Permission.backups_manage: {UserRole.administrator},
    Permission.competition_reset: {UserRole.administrator},
    Permission.demo_manage: {UserRole.administrator},
    Permission.clubs_merge: {UserRole.administrator, UserRole.chief_judge},
    Permission.participants_merge: {UserRole.administrator, UserRole.chief_judge},
    Permission.judge_conflicts_resolve: {UserRole.administrator, UserRole.chief_judge, UserRole.secretary},
}
for role, permissions in STANDARD_PERMISSIONS.items():
    permissions.update(permission for permission, parent in PERMISSION_PARENTS.items()
                       if parent in {item.value for item in permissions} and role in DEFAULT_PERMISSION_ROLES.get(permission, set(UserRole)))
    permissions.difference_update(permission for permission, roles in DEFAULT_PERMISSION_ROLES.items() if role not in roles)


def effective_permissions(db: Session, role: UserRole) -> set[Permission]:
    if role == UserRole.administrator:
        return set(Permission)
    rows = list(db.scalars(select(RolePermission).where(RolePermission.role == role)).all())
    if not rows:
        return set(STANDARD_PERMISSIONS[role])
    stored = {row.permission: row.is_allowed for row in rows}
    allowed = {permission for permission in Permission if stored.get(permission.value, False)}
    allowed.update(permission for permission, parent in PERMISSION_PARENTS.items()
                   if permission.value not in stored and stored.get(parent, False)
                   and role in DEFAULT_PERMISSION_ROLES.get(permission, set(UserRole)))
    return allowed


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
