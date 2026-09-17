"""Store the latest connection report separately from versioned user accounts."""
from alembic import op
import sqlalchemy as sa

revision = "0028_user_presence"
down_revision = "0027_route_groups"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("user_presence",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("admins.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("unstable", sa.Boolean(), nullable=False),
    )


def downgrade():
    op.drop_table("user_presence")
