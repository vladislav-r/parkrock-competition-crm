"""Configurable final participation per age category.

Revision ID: 0011_final_participation
Revises: 0010_final_results
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011_final_participation"
down_revision: Union[str, Sequence[str], None] = "0010_final_results"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "age_groups",
        sa.Column("participates_in_final", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.execute("UPDATE age_groups SET participates_in_final = false WHERE min_age = 7 AND max_age = 9")


def downgrade() -> None:
    op.drop_column("age_groups", "participates_in_final")
