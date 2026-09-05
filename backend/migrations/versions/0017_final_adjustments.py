"""Add qualification start and public result detail settings.

Revision ID: 0017_final_adjustments
Revises: 0016_judge_final_route
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0017_final_adjustments"
down_revision: Union[str, Sequence[str], None] = "0016_judge_final_route"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("qualification_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "events",
        sa.Column("public_result_details_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("events", "public_result_details_enabled")
    op.drop_column("events", "qualification_started_at")
