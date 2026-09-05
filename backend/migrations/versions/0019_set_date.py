"""Add an optional competition date to sets.

Revision ID: 0019_set_date
Revises: 0018_preparation_stage
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0019_set_date"
down_revision: Union[str, Sequence[str], None] = "0018_preparation_stage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("competition_sets", sa.Column("scheduled_on", sa.Date(), nullable=True))
    op.create_index("ix_competition_sets_scheduled_on", "competition_sets", ["scheduled_on"])


def downgrade() -> None:
    op.drop_index("ix_competition_sets_scheduled_on", table_name="competition_sets")
    op.drop_column("competition_sets", "scheduled_on")
