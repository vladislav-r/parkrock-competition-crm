"""Preserve delayed judge results for explicit conflict resolution."""
from alembic import op
import sqlalchemy as sa

revision = "0022_judge_conflicts"
down_revision = "0021_export_settings"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "judge_result_conflicts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("final_result_id", sa.Uuid(), sa.ForeignKey("final_category_results.id", ondelete="SET NULL")),
        sa.Column("final_route_id", sa.Uuid(), sa.ForeignKey("final_routes.id", ondelete="SET NULL")),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("admins.id", ondelete="SET NULL")),
        sa.Column("details_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolution", sa.String(20)),
        sa.Column("resolved_by_id", sa.Uuid(), sa.ForeignKey("admins.id", ondelete="SET NULL")),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_judge_result_conflicts_event_id", "judge_result_conflicts", ["event_id"])


def downgrade():
    op.drop_table("judge_result_conflicts")
