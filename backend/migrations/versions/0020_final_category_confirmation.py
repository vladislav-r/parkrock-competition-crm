"""Add per-category final result confirmations.

Revision ID: 0020_final_confirmation
Revises: 0019_set_date
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0020_final_confirmation"
down_revision: Union[str, Sequence[str], None] = "0019_set_date"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "qualification_category_snapshots",
        sa.Column("final_confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "qualification_category_snapshots",
        sa.Column("final_confirmed_by_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "qualification_category_snapshots",
        sa.Column("final_signature", sa.String(length=64), nullable=True),
    )
    op.create_foreign_key(
        "fk_qualification_snapshot_final_confirmed_by",
        "qualification_category_snapshots",
        "admins",
        ["final_confirmed_by_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_qualification_snapshot_final_confirmed_by",
        "qualification_category_snapshots",
        type_="foreignkey",
    )
    op.drop_column("qualification_category_snapshots", "final_signature")
    op.drop_column("qualification_category_snapshots", "final_confirmed_by_id")
    op.drop_column("qualification_category_snapshots", "final_confirmed_at")
