"""Add users roles, permissions and immutable audit log.

Revision ID: 0003_users_roles_audit
Revises: 0002_concurrency
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0003_users_roles_audit"
down_revision: Union[str, Sequence[str], None] = "0002_concurrency"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLES = ("reception", "secretary", "chief_judge", "administrator", "route_judge")
PERMISSIONS = (
    "dashboard.view", "participants.view", "participants.manage", "participants.import",
    "results.manage", "sets.manage", "routes.manage", "settings.manage", "users.manage",
    "roles.manage", "audit.view", "exports.create", "final.manage", "judge.results",
)
STANDARD = {
    "reception": {"dashboard.view", "participants.view", "participants.manage", "participants.import"},
    "secretary": set(PERMISSIONS) - {"users.manage", "roles.manage", "judge.results"},
    "chief_judge": set(PERMISSIONS) - {"users.manage", "roles.manage", "judge.results"},
    "administrator": set(PERMISSIONS),
    "route_judge": {"dashboard.view", "participants.view", "judge.results"},
}


def upgrade() -> None:
    bind = op.get_bind()
    user_role = postgresql.ENUM(*ROLES, name="userrole", create_type=False)
    user_role.create(bind, checkfirst=True)

    op.add_column("admins", sa.Column(
        "role", user_role, server_default="administrator", nullable=False,
    ))
    op.add_column("admins", sa.Column("assigned_route_id", sa.Uuid(), nullable=True))
    op.add_column("admins", sa.Column("version", sa.Integer(), server_default="1", nullable=False))
    op.create_foreign_key(
        "fk_admins_assigned_route", "admins", "routes", ["assigned_route_id"], ["id"], ondelete="SET NULL",
    )

    op.create_table(
        "role_permissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("permission", sa.String(100), nullable=False),
        sa.Column("is_allowed", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("role", "permission", name="uq_role_permission"),
    )
    op.create_index("ix_role_permissions_role", "role_permissions", ["role"])
    role_permissions = sa.table(
        "role_permissions",
        sa.column("id", sa.Uuid()), sa.column("role", user_role),
        sa.column("permission", sa.String()), sa.column("is_allowed", sa.Boolean()),
    )
    op.bulk_insert(role_permissions, [
        {"id": uuid.uuid4(), "role": role, "permission": permission,
         "is_allowed": permission in STANDARD[role]}
        for role in ROLES for permission in PERMISSIONS
    ])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_email", sa.String(255), nullable=False),
        sa.Column("actor_role", sa.String(50), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=False),
        sa.Column("target_id", sa.String(100), nullable=False),
        sa.Column("old_value_json", sa.Text(), nullable=True),
        sa.Column("new_value_json", sa.Text(), nullable=True),
        sa.Column("result", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["admins.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("actor_id", "action", "target_type", "result", "created_at"):
        op.create_index(f"ix_audit_logs_{column}", "audit_logs", [column])

    op.execute("""
        CREATE FUNCTION protect_audit_logs() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs is append-only';
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER audit_logs_immutable
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION protect_audit_logs();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_logs_immutable ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS protect_audit_logs()")
    op.drop_table("audit_logs")
    op.drop_table("role_permissions")
    op.drop_constraint("fk_admins_assigned_route", "admins", type_="foreignkey")
    op.drop_column("admins", "version")
    op.drop_column("admins", "assigned_route_id")
    op.drop_column("admins", "role")
    postgresql.ENUM(name="userrole").drop(op.get_bind(), checkfirst=True)
