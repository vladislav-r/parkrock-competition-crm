"""Add zero-final categories, grade points and repeatable applications.

Revision ID: 0014_current_corrections
Revises: 0013_application_files
"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0014_current_corrections"
down_revision: Union[str, Sequence[str], None] = "0013_application_files"
branch_labels = None
depends_on = None


GRADES = [
    f"{level}{suffix}"
    for level in (5, 6, 7, 8)
    for suffix in ("A", "A+", "B", "B+", "C", "C+")
]


def upgrade() -> None:
    op.drop_constraint("ck_age_group_finalist_count_positive", "age_groups", type_="check")
    op.create_check_constraint("ck_age_group_finalist_count_nonnegative", "age_groups", "finalist_count >= 0")
    op.create_table(
        "route_grade_points",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("grade", sa.String(length=20), nullable=False),
        sa.Column("points", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("points IS NULL OR points >= 0", name="ck_route_grade_points_nonnegative"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "grade", name="uq_route_grade_points_event_grade"),
    )
    op.create_index("ix_route_grade_points_event_id", "route_grade_points", ["event_id"])
    connection = op.get_bind()
    event_ids = [row[0] for row in connection.execute(sa.text("SELECT id FROM events"))]
    grade_table = sa.table(
        "route_grade_points",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("event_id", postgresql.UUID(as_uuid=True)),
        sa.column("grade", sa.String()),
        sa.column("points", sa.Integer()),
        sa.column("version", sa.Integer()),
    )
    if event_ids:
        op.bulk_insert(grade_table, [
            {"id": uuid.uuid4(), "event_id": event_id, "grade": grade, "points": None, "version": 1}
            for event_id in event_ids for grade in GRADES
        ])
    op.execute("UPDATE routes SET points = 0")
    op.execute("UPDATE age_groups SET finalist_count = 0, participates_in_final = false WHERE min_age = 7 AND max_age = 9")

    op.add_column("applications", sa.Column("import_count", sa.Integer(), nullable=False, server_default="0"))
    op.execute("UPDATE applications SET import_count = 1 WHERE status = 'imported'")


def downgrade() -> None:
    op.execute("UPDATE age_groups SET finalist_count = 10 WHERE finalist_count = 0")
    op.drop_constraint("ck_age_group_finalist_count_nonnegative", "age_groups", type_="check")
    op.create_check_constraint("ck_age_group_finalist_count_positive", "age_groups", "finalist_count > 0")
    op.drop_column("applications", "import_count")
    op.drop_index("ix_route_grade_points_event_id", table_name="route_grade_points")
    op.drop_table("route_grade_points")
