"""Configurable public result refresh intervals."""
from alembic import op
import sqlalchemy as sa

revision = "0024_public_refresh"
down_revision = "0023_young_final_opt_in"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("events", sa.Column("qualification_refresh_seconds", sa.Integer(), nullable=False, server_default="30"))
    op.add_column("events", sa.Column("final_refresh_seconds", sa.Integer(), nullable=False, server_default="10"))


def downgrade():
    op.drop_column("events", "final_refresh_seconds")
    op.drop_column("events", "qualification_refresh_seconds")
