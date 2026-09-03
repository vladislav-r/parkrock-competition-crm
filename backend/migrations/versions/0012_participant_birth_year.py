"""Store the festival application birth year explicitly.

Revision ID: 0012_birth_year
Revises: 0011_final_participation
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0012_birth_year"
down_revision: Union[str, Sequence[str], None] = "0011_final_participation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("participants", sa.Column("birth_year", sa.Integer(), nullable=True))
    op.execute("UPDATE participants SET birth_year = EXTRACT(YEAR FROM birth_date)::integer WHERE birth_year IS NULL")


def downgrade() -> None:
    op.drop_column("participants", "birth_year")
