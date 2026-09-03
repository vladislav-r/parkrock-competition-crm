"""Allow one club to have multiple representatives.

Revision ID: 0015_club_representatives
Revises: 0014_current_corrections
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0015_club_representatives"
down_revision: Union[str, Sequence[str], None] = "0014_current_corrections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clubs", sa.Column(
        "normalized_representative", sa.String(length=200), nullable=False, server_default="",
    ))
    op.execute("""
        UPDATE clubs
        SET normalized_representative = lower(regexp_replace(trim(representative), '\\s+', ' ', 'g'))
    """)
    op.drop_constraint("uq_club_event_normalized_name", "clubs", type_="unique")
    op.create_unique_constraint(
        "uq_club_event_name_representative", "clubs",
        ["event_id", "normalized_name", "normalized_representative"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_club_event_name_representative", "clubs", type_="unique")
    op.create_unique_constraint("uq_club_event_normalized_name", "clubs", ["event_id", "normalized_name"])
    op.drop_column("clubs", "normalized_representative")
