"""Editable age categories and finisher medals.

Revision ID: 0007_categories_finishers
Revises: 0006_club_edit_permission
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0007_categories_finishers"
down_revision: Union[str, Sequence[str], None] = "0006_club_edit_permission"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("age_groups", "max_age", existing_type=sa.Integer(), nullable=True)
    for column in (
        "bronze_min_points", "bronze_max_points", "silver_min_points",
        "silver_max_points", "gold_min_points", "gold_max_points",
    ):
        op.add_column("age_groups", sa.Column(column, sa.Integer(), nullable=True))
    op.add_column("age_groups", sa.Column("version", sa.Integer(), server_default="1", nullable=False))
    op.add_column("published_results", sa.Column("is_finisher", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("published_results", sa.Column("medal", sa.String(10), nullable=True))

    # Новая базовая конфигурация: без юниоров 19–20, взрослые с 19 лет без верхней границы.
    op.execute("DELETE FROM age_groups WHERE name IN ('Юниоры 19-20', 'Юниорки 19-20')")
    op.execute("""
        UPDATE age_groups SET min_age = 19, max_age = NULL
        WHERE name IN ('Мужчины', 'Женщины')
    """)
    sex_type = postgresql.ENUM("male", "female", name="sex", create_type=False)
    groups = sa.table(
        "age_groups", sa.column("id", sa.Uuid()), sa.column("event_id", sa.Uuid()),
        sa.column("name", sa.String()), sa.column("sex", sex_type), sa.column("min_age", sa.Integer()),
        sa.column("max_age", sa.Integer()), sa.column("sort_order", sa.Integer()), sa.column("version", sa.Integer()),
    )
    connection = op.get_bind()
    event_ids = [row[0] for row in connection.execute(sa.text("SELECT id FROM events"))]
    for event_id in event_ids:
        for sex, name, order in (("male", "Мальчики 7-9", 0), ("female", "Девочки 7-9", 1)):
            exists = connection.execute(sa.text(
                "SELECT 1 FROM age_groups WHERE event_id=:event_id AND sex=:sex AND min_age=7 AND max_age=9"
            ), {"event_id": event_id, "sex": sex}).first()
            if not exists:
                op.bulk_insert(groups, [{
                    "id": uuid.uuid4(), "event_id": event_id, "name": name, "sex": sex,
                    "min_age": 7, "max_age": 9, "sort_order": order, "version": 1,
                }])
    op.execute("""
        WITH ordered AS (
            SELECT id, (ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY min_age, CASE sex WHEN 'male' THEN 0 ELSE 1 END) - 1)::int AS new_order
            FROM age_groups
        )
        UPDATE age_groups SET sort_order = ordered.new_order FROM ordered WHERE age_groups.id = ordered.id
    """)


def downgrade() -> None:
    op.drop_column("published_results", "medal")
    op.drop_column("published_results", "is_finisher")
    op.drop_column("age_groups", "version")
    for column in (
        "gold_max_points", "gold_min_points", "silver_max_points",
        "silver_min_points", "bronze_max_points", "bronze_min_points",
    ):
        op.drop_column("age_groups", column)
    op.execute("UPDATE age_groups SET max_age = 99 WHERE max_age IS NULL")
    op.alter_column("age_groups", "max_age", existing_type=sa.Integer(), nullable=False)
