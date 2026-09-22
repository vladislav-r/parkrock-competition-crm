"""Persist category order within the two final streams."""
from alembic import op
import sqlalchemy as sa

revision = "0031_final_stream_order"
down_revision = "0030_public_display_settings"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("final_category_routes", sa.Column("stream_order", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("final_category_routes", "stream_order")
