"""Add participant application lifecycle fields.

Revision ID: 0004_participant_applications
Revises: 0003_users_roles_audit
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0004_participant_applications"
down_revision: Union[str, Sequence[str], None] = "0003_users_roles_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    application_type = postgresql.ENUM("collective", "individual", name="applicationtype", create_type=False)
    participant_source = postgresql.ENUM("import_file", "manual", name="participantsource", create_type=False)
    application_type.create(bind, checkfirst=True)
    participant_source.create(bind, checkfirst=True)

    op.add_column("events", sa.Column("final_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("participants", sa.Column(
        "application_type", application_type, server_default="collective", nullable=False,
    ))
    op.add_column("participants", sa.Column("merch_size", sa.String(30), nullable=True))
    op.add_column("participants", sa.Column("is_paid", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("participants", sa.Column("merch_issued", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("participants", sa.Column(
        "source", participant_source, server_default="import_file", nullable=False,
    ))
    op.add_column("participants", sa.Column("import_operation_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_participants_import_operation", "participants", "operation_records",
        ["import_operation_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_participants_import_operation_id", "participants", ["import_operation_id"])


def downgrade() -> None:
    op.drop_index("ix_participants_import_operation_id", table_name="participants")
    op.drop_constraint("fk_participants_import_operation", "participants", type_="foreignkey")
    for column in ("import_operation_id", "source", "merch_issued", "is_paid", "merch_size", "application_type"):
        op.drop_column("participants", column)
    op.drop_column("events", "final_started_at")
    postgresql.ENUM(name="participantsource").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="applicationtype").drop(op.get_bind(), checkfirst=True)
