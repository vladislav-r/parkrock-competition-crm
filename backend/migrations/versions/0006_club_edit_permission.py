"""Add club editing permission.

Revision ID: 0006_club_edit_permission
Revises: 0005_reception_clubs
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0006_club_edit_permission"
down_revision: Union[str, Sequence[str], None] = "0005_reception_clubs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    user_role = postgresql.ENUM(
        "reception", "secretary", "chief_judge", "administrator", "route_judge",
        name="userrole", create_type=False,
    )
    role_permissions = sa.table(
        "role_permissions", sa.column("id", sa.Uuid()), sa.column("role", user_role),
        sa.column("permission", sa.String()), sa.column("is_allowed", sa.Boolean()),
    )
    allowed = {"secretary", "chief_judge", "administrator"}
    op.bulk_insert(role_permissions, [
        {"id": uuid.uuid4(), "role": role, "permission": "clubs.manage", "is_allowed": role in allowed}
        for role in ("reception", "secretary", "chief_judge", "administrator", "route_judge")
    ])


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions WHERE permission = 'clubs.manage'")
