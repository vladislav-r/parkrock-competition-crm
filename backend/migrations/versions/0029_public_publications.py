"""Store atomic public result publications per festival."""
from alembic import op
import sqlalchemy as sa

revision = "0029_public_publications"
down_revision = "0028_user_presence"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("public_publications",
        sa.Column("source_stage", sa.String(30), nullable=False),
        sa.Column("publication_id", sa.Uuid(), unique=True, nullable=False),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("events.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )


def downgrade():
    op.drop_table("public_publications")
