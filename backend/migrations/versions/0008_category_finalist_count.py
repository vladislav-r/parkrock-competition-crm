"""Configurable finalist count per category.

Revision ID: 0008_category_finalist_count
Revises: 0007_categories_finishers
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_category_finalist_count"
down_revision: Union[str, Sequence[str], None] = "0007_categories_finishers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("age_groups", sa.Column("finalist_count", sa.Integer(), server_default="10", nullable=False))
    op.create_check_constraint("ck_age_group_finalist_count_positive", "age_groups", "finalist_count > 0")


def downgrade() -> None:
    op.drop_constraint("ck_age_group_finalist_count_positive", "age_groups", type_="check")
    op.drop_column("age_groups", "finalist_count")
