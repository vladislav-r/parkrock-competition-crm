"""Store XLSX applications received from the landing page.

Revision ID: 0013_application_files
Revises: 0012_birth_year
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0013_application_files"
down_revision: Union[str, Sequence[str], None] = "0012_birth_year"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=150), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("file_data", sa.LargeBinary(), nullable=False),
        sa.Column("participant_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("overflow_sets", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("imported_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("import_operation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint("file_size > 0", name="ck_application_file_size_positive"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["imported_by_id"], ["admins.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["import_operation_id"], ["operation_records.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "content_sha256", name="uq_application_event_content"),
    )
    op.create_index("ix_applications_event_id", "applications", ["event_id"])


def downgrade() -> None:
    op.drop_index("ix_applications_event_id", table_name="applications")
    op.drop_table("applications")
