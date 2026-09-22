"""Settings for the printable safety register."""
from alembic import op
import sqlalchemy as sa
revision = "0032_safety_exports"
down_revision = "0031_final_stream_order"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("events", sa.Column("safety_export_settings", sa.JSON(), nullable=False, server_default="{}"))

def downgrade():
    op.drop_column("events", "safety_export_settings")
