"""Store configurable public display preferences."""
from alembic import op
import sqlalchemy as sa

revision = "0030_public_display_settings"
down_revision = "0029_public_publications"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("events", sa.Column("public_display_settings", sa.JSON(), nullable=False, server_default="{}"))


def downgrade():
    op.drop_column("events", "public_display_settings")
