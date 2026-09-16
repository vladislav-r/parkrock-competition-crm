"""Configurable route ranges; preserve every route and its current points."""
import uuid

from alembic import op
import sqlalchemy as sa

revision = "0027_route_groups"
down_revision = "0026_custom_roles"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("route_groups",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_grade", sa.String(20), nullable=False),
        sa.Column("to_grade", sa.String(20), nullable=False),
        sa.Column("color", sa.String(7), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("points >= 0", name="ck_route_group_points_nonnegative"))
    op.create_index("ix_route_groups_event_id", "route_groups", ["event_id"])
    op.add_column("routes", sa.Column("group_id", sa.Uuid(), sa.ForeignKey("route_groups.id"), nullable=True))
    op.create_index("ix_routes_group_id", "routes", ["group_id"])
    connection = op.get_bind()
    # Keep distinct prices even if legacy routes share a grade. No score recalculation.
    for row in connection.execute(sa.text("SELECT DISTINCT event_id, grade, points FROM routes")).mappings().all():
        values = dict(row, id=uuid.uuid4())
        connection.execute(sa.text("INSERT INTO route_groups (id,event_id,from_grade,to_grade,color,points,version) VALUES (:id,:event_id,:grade,:grade,'#ffffff',:points,1)"), values)
        connection.execute(sa.text("UPDATE routes SET group_id=:id WHERE event_id=:event_id AND grade=:grade AND points=:points"), values)


def downgrade():
    op.drop_index("ix_routes_group_id", table_name="routes")
    op.drop_column("routes", "group_id")
    op.drop_table("route_groups")
