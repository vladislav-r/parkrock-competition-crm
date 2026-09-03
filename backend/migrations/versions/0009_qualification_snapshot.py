"""Qualification confirmation and immutable final snapshot.

Revision ID: 0009_qualification_snapshot
Revises: 0008_category_finalist_count
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0009_qualification_snapshot"
down_revision: Union[str, Sequence[str], None] = "0008_category_finalist_count"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    stage = postgresql.ENUM("qualification", "final", "completed", name="eventstage")
    stage.create(op.get_bind(), checkfirst=True)
    op.add_column("events", sa.Column("stage", stage, server_default="qualification", nullable=False))
    op.add_column("events", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("events", sa.Column("version", sa.Integer(), server_default="1", nullable=False))
    op.execute("UPDATE events SET stage='final' WHERE final_started_at IS NOT NULL")

    op.add_column("age_groups", sa.Column("qualification_confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("age_groups", sa.Column("qualification_confirmed_by_id", sa.Uuid(), nullable=True))
    op.add_column("age_groups", sa.Column("qualification_signature", sa.String(64), nullable=True))
    op.create_foreign_key(
        "fk_age_group_qualification_confirmed_by", "age_groups", "admins",
        ["qualification_confirmed_by_id"], ["id"], ondelete="SET NULL",
    )

    sex = postgresql.ENUM("male", "female", name="sex", create_type=False)
    op.create_table(
        "qualification_category_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("age_group_id", sa.Uuid(), sa.ForeignKey("age_groups.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("sex", sex, nullable=False),
        sa.Column("min_age", sa.Integer(), nullable=False),
        sa.Column("max_age", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("finalist_count", sa.Integer(), nullable=False),
        sa.Column("settings_json", sa.Text(), nullable=False),
        sa.Column("signature", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id", "age_group_id", name="uq_qualification_snapshot_group"),
    )
    op.create_index("ix_qualification_category_snapshots_event_id", "qualification_category_snapshots", ["event_id"])
    op.create_index("ix_qualification_category_snapshots_age_group_id", "qualification_category_snapshots", ["age_group_id"])
    op.create_table(
        "qualification_result_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category_snapshot_id", sa.Uuid(), sa.ForeignKey("qualification_category_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("participant_id", sa.Uuid(), sa.ForeignKey("participants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("start_number", sa.Integer(), nullable=False),
        sa.Column("surname", sa.String(100), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("patronymic", sa.String(100), nullable=False, server_default=""),
        sa.Column("club", sa.String(200), nullable=False),
        sa.Column("completed_count", sa.Integer(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("place", sa.Integer(), nullable=False),
        sa.Column("is_finalist", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("exit_order", sa.Integer(), nullable=True),
        sa.Column("completed_routes_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("category_snapshot_id", "participant_id", name="uq_qualification_snapshot_participant"),
    )
    op.create_index("ix_qualification_result_snapshots_event_id", "qualification_result_snapshots", ["event_id"])
    op.create_index("ix_qualification_result_snapshots_category_snapshot_id", "qualification_result_snapshots", ["category_snapshot_id"])
    op.create_index("ix_qualification_result_snapshots_participant_id", "qualification_result_snapshots", ["participant_id"])


def downgrade() -> None:
    op.drop_table("qualification_result_snapshots")
    op.drop_table("qualification_category_snapshots")
    op.drop_constraint("fk_age_group_qualification_confirmed_by", "age_groups", type_="foreignkey")
    op.drop_column("age_groups", "qualification_signature")
    op.drop_column("age_groups", "qualification_confirmed_by_id")
    op.drop_column("age_groups", "qualification_confirmed_at")
    op.drop_column("events", "version")
    op.drop_column("events", "completed_at")
    op.drop_column("events", "stage")
    postgresql.ENUM(name="eventstage").drop(op.get_bind(), checkfirst=True)
