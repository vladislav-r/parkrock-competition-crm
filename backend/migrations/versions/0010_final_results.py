"""Final routes, category assignments, attempts and calculated results.

Revision ID: 0010_final_results
Revises: 0009_qualification_snapshot
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010_final_results"
down_revision: Union[str, Sequence[str], None] = "0009_qualification_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "final_routes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("event_id", "number", name="uq_final_route_event_number"),
    )
    op.create_index("ix_final_routes_event_id", "final_routes", ["event_id"])
    op.create_table(
        "final_category_routes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("age_group_id", sa.Uuid(), sa.ForeignKey("age_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("final_route_id", sa.Uuid(), sa.ForeignKey("final_routes.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("age_group_id", "final_route_id", name="uq_final_category_route"),
    )
    op.create_index("ix_final_category_routes_event_id", "final_category_routes", ["event_id"])
    op.create_index("ix_final_category_routes_age_group_id", "final_category_routes", ["age_group_id"])
    op.create_index("ix_final_category_routes_final_route_id", "final_category_routes", ["final_route_id"])
    op.create_table(
        "final_category_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category_snapshot_id", sa.Uuid(), sa.ForeignKey("qualification_category_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("qualification_result_snapshot_id", sa.Uuid(), sa.ForeignKey("qualification_result_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("participant_id", sa.Uuid(), sa.ForeignKey("participants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("score_tenths", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("top_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("zone_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("top_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("zone_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("place", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("qualification_result_snapshot_id", name="uq_final_result_snapshot"),
    )
    op.create_index("ix_final_category_results_event_id", "final_category_results", ["event_id"])
    op.create_index("ix_final_category_results_category_snapshot_id", "final_category_results", ["category_snapshot_id"])
    op.create_index("ix_final_category_results_qualification_result_snapshot_id", "final_category_results", ["qualification_result_snapshot_id"])
    op.create_index("ix_final_category_results_participant_id", "final_category_results", ["participant_id"])
    op.create_table(
        "final_route_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("final_category_result_id", sa.Uuid(), sa.ForeignKey("final_category_results.id", ondelete="CASCADE"), nullable=False),
        sa.Column("final_route_id", sa.Uuid(), sa.ForeignKey("final_routes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("zone_attempt", sa.Integer(), nullable=True),
        sa.Column("top_attempt", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("final_category_result_id", "final_route_id", name="uq_final_result_route"),
    )
    op.create_index("ix_final_route_attempts_event_id", "final_route_attempts", ["event_id"])
    op.create_index("ix_final_route_attempts_final_category_result_id", "final_route_attempts", ["final_category_result_id"])
    op.create_index("ix_final_route_attempts_final_route_id", "final_route_attempts", ["final_route_id"])

    bind = op.get_bind()
    event_ids = [row.id for row in bind.execute(sa.text("SELECT id FROM events"))]
    final_routes = sa.table("final_routes", sa.column("id", sa.Uuid()), sa.column("event_id", sa.Uuid()), sa.column("number", sa.Integer()), sa.column("name", sa.String()), sa.column("version", sa.Integer()))
    for event_id in event_ids:
        op.bulk_insert(final_routes, [{
            "id": uuid.uuid5(uuid.NAMESPACE_URL, f"parkrock:final-route:{event_id}:{number}"),
            "event_id": event_id, "number": number, "name": f"Финал {number}", "version": 1,
        } for number in range(1, 9)])
    op.execute("""
        INSERT INTO final_category_results (id, event_id, category_snapshot_id, qualification_result_snapshot_id, participant_id, score_tenths, top_count, zone_count, top_attempts, zone_attempts, version)
        SELECT md5('parkrock:final-result:' || qrs.id::text)::uuid, qrs.event_id, qrs.category_snapshot_id, qrs.id, qrs.participant_id, 0, 0, 0, 0, 0, 1
        FROM qualification_result_snapshots qrs
        WHERE qrs.is_finalist = true
    """)


def downgrade() -> None:
    op.drop_table("final_route_attempts")
    op.drop_table("final_category_results")
    op.drop_table("final_category_routes")
    op.drop_table("final_routes")
