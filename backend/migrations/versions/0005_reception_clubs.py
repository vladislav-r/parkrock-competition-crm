"""Add stable clubs directory.

Revision ID: 0005_reception_clubs
Revises: 0004_participant_applications
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_reception_clubs"
down_revision: Union[str, Sequence[str], None] = "0004_participant_applications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "clubs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("normalized_name", sa.String(200), nullable=False),
        sa.Column("representative", sa.String(200), server_default="", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "normalized_name", name="uq_club_event_normalized_name"),
    )
    op.create_index("ix_clubs_event_id", "clubs", ["event_id"])
    op.add_column("participants", sa.Column("club_id", sa.Uuid(), nullable=True))
    op.execute("""
        INSERT INTO clubs (id, event_id, name, normalized_name, representative, version)
        SELECT gen_random_uuid(), event_id,
               MIN(COALESCE(NULLIF(BTRIM(club), ''), 'Без клуба')),
               LOWER(COALESCE(NULLIF(REGEXP_REPLACE(BTRIM(club), '\\s+', ' ', 'g'), ''), 'без клуба')),
               COALESCE(MAX(NULLIF(BTRIM(representative), '')), ''), 1
        FROM participants
        GROUP BY event_id, LOWER(COALESCE(NULLIF(REGEXP_REPLACE(BTRIM(club), '\\s+', ' ', 'g'), ''), 'без клуба'))
    """)
    op.execute("""
        UPDATE participants AS participant
        SET club_id = club.id
        FROM clubs AS club
        WHERE club.event_id = participant.event_id
          AND club.normalized_name = LOWER(COALESCE(NULLIF(REGEXP_REPLACE(BTRIM(participant.club), '\\s+', ' ', 'g'), ''), 'без клуба'))
    """)
    op.alter_column("participants", "club_id", nullable=False)
    op.create_foreign_key(
        "fk_participants_club", "participants", "clubs", ["club_id"], ["id"], ondelete="RESTRICT",
    )
    op.create_index("ix_participants_club_id", "participants", ["club_id"])


def downgrade() -> None:
    op.drop_index("ix_participants_club_id", table_name="participants")
    op.drop_constraint("fk_participants_club", "participants", type_="foreignkey")
    op.drop_column("participants", "club_id")
    op.drop_index("ix_clubs_event_id", table_name="clubs")
    op.drop_table("clubs")
