"""Initial ParkRock Hub schema.

Revision ID: 0001_initial
Revises:
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

sex = postgresql.ENUM("male", "female", name="sex", create_type=False)
set_status = postgresql.ENUM("draft", "confirmed", "reopened", name="setstatus", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    sex.create(bind, checkfirst=True)
    set_status.create(bind, checkfirst=True)

    op.create_table(
        "admins",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_admins_email", "admins", ["email"], unique=True)
    op.create_table(
        "events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("location", sa.String(255), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "age_groups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("sex", sex, nullable=False),
        sa.Column("min_age", sa.Integer(), nullable=False),
        sa.Column("max_age", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "name", name="uq_age_group_event_name"),
    )
    op.create_index("ix_age_groups_event_id", "age_groups", ["event_id"])
    op.create_table(
        "competition_sets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("time_label", sa.String(100), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("status", set_status, nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("capacity > 0", name="ck_set_capacity_positive"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_competition_sets_event_id", "competition_sets", ["event_id"])
    op.create_table(
        "routes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("grade", sa.String(20), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.CheckConstraint("points >= 0", name="ck_route_points_nonnegative"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "number", name="uq_route_event_number"),
    )
    op.create_index("ix_routes_event_id", "routes", ["event_id"])
    op.create_table(
        "participants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("set_id", sa.Uuid(), nullable=False),
        sa.Column("start_number", sa.Integer(), nullable=False),
        sa.Column("surname", sa.String(100), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("patronymic", sa.String(100), nullable=False),
        sa.Column("birth_date", sa.Date(), nullable=False),
        sa.Column("sex", sex, nullable=False),
        sa.Column("sport_rank", sa.String(50), nullable=False),
        sa.Column("club", sa.String(200), nullable=False),
        sa.Column("representative", sa.String(200), nullable=False),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("start_number > 0", name="ck_participant_start_number_positive"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["set_id"], ["competition_sets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "start_number", name="uq_participant_event_start_number"),
    )
    op.create_index("ix_participants_event_id", "participants", ["event_id"])
    op.create_index("ix_participants_set_id", "participants", ["set_id"])
    op.create_table(
        "ascents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("participant_id", sa.Uuid(), nullable=False),
        sa.Column("route_id", sa.Uuid(), nullable=False),
        sa.Column("is_completed", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["route_id"], ["routes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("participant_id", "route_id", name="uq_ascent_participant_route"),
    )
    op.create_index("ix_ascents_participant_id", "ascents", ["participant_id"])
    op.create_table(
        "published_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("set_id", sa.Uuid(), nullable=False),
        sa.Column("participant_id", sa.Uuid(), nullable=False),
        sa.Column("group_name", sa.String(100), nullable=False),
        sa.Column("completed_count", sa.Integer(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("place", sa.Integer(), nullable=False),
        sa.Column("is_finalist", sa.Boolean(), nullable=False),
        sa.Column("completed_route_ids", sa.String(), nullable=False),
        sa.Column("completed_routes_json", sa.String(), server_default="[]", nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["set_id"], ["competition_sets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("participant_id", name="uq_published_participant"),
    )
    op.create_index("ix_published_results_event_id", "published_results", ["event_id"])
    op.create_index("ix_published_results_group_name", "published_results", ["group_name"])
    op.create_index("ix_published_results_set_id", "published_results", ["set_id"])


def downgrade() -> None:
    op.drop_table("published_results")
    op.drop_table("ascents")
    op.drop_table("participants")
    op.drop_table("routes")
    op.drop_table("competition_sets")
    op.drop_table("age_groups")
    op.drop_table("events")
    op.drop_table("admins")
    bind = op.get_bind()
    set_status.drop(bind, checkfirst=True)
    sex.drop(bind, checkfirst=True)
