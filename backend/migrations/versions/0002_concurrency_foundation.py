"""Add optimistic versions and operation records.

Revision ID: 0002_concurrency
Revises: 0001_initial
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_concurrency"
down_revision: Union[str, Sequence[str], None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table_name in ("competition_sets", "routes", "participants"):
        op.add_column(
            table_name,
            sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        )
    op.create_table(
        "operation_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("admin_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=False),
        sa.Column("target_id", sa.String(100), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["admin_id"], ["admins.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_operation_records_admin_id", "operation_records", ["admin_id"])


def downgrade() -> None:
    op.drop_table("operation_records")
    for table_name in ("participants", "routes", "competition_sets"):
        op.drop_column(table_name, "version")
