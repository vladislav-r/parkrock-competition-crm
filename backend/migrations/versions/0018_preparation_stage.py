"""Add an explicit preparation stage.

Revision ID: 0018_preparation_stage
Revises: 0017_final_adjustments
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0018_preparation_stage"
down_revision: Union[str, Sequence[str], None] = "0017_final_adjustments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE eventstage ADD VALUE IF NOT EXISTS 'preparation' BEFORE 'qualification'")
    op.execute(
        "UPDATE events SET stage = 'preparation' "
        "WHERE stage = 'qualification' AND qualification_started_at IS NULL"
    )


def downgrade() -> None:
    op.execute("UPDATE events SET stage = 'qualification' WHERE stage = 'preparation'")
