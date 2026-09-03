"""Assign route judges to final routes.

Revision ID: 0016_judge_final_route
Revises: 0015_club_representatives
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0016_judge_final_route"
down_revision: Union[str, Sequence[str], None] = "0015_club_representatives"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("admins", sa.Column("assigned_final_route_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_admins_assigned_final_route", "admins", "final_routes",
        ["assigned_final_route_id"], ["id"], ondelete="SET NULL",
    )
    op.execute("""
        UPDATE admins AS admin
        SET assigned_final_route_id = final_route.id
        FROM routes AS route
        JOIN final_routes AS final_route
          ON final_route.event_id = route.event_id AND final_route.number = route.number
        WHERE admin.assigned_route_id = route.id
          AND admin.role = 'route_judge'
    """)


def downgrade() -> None:
    op.drop_constraint("fk_admins_assigned_final_route", "admins", type_="foreignkey")
    op.drop_column("admins", "assigned_final_route_id")
