"""Add protocol export header settings.

Revision ID: 0021_export_settings
Revises: 0020_final_confirmation
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0021_export_settings"
down_revision: Union[str, Sequence[str], None] = "0020_final_confirmation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    fields = (
        ("export_competition_name", 255),
        ("export_location", 255),
        ("export_dates", 255),
        ("export_official_name", 255),
        ("export_official_qualification", 100),
    )
    for name, length in fields:
        op.add_column(
            "events",
            sa.Column(name, sa.String(length=length), nullable=False, server_default=""),
        )
    op.execute("UPDATE events SET export_competition_name = title, export_location = location")


def downgrade() -> None:
    for name in (
        "export_official_qualification",
        "export_official_name",
        "export_dates",
        "export_location",
        "export_competition_name",
    ):
        op.drop_column("events", name)
