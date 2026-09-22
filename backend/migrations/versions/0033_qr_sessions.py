"""Revocable single sessions and permanent personal QR credentials."""
from alembic import op
import sqlalchemy as sa

revision = "0033_qr_sessions"
down_revision = "0032_safety_exports"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_access",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("admins.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("session_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("session_end_reason", sa.String(30), nullable=True),
        sa.Column("qr_hash", sa.String(64), unique=True, nullable=True),
        sa.Column("qr_session_hours", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("qr_session_hours BETWEEN 1 AND 168"),
    )
    op.create_table(
        "auth_rate_limits",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("auth_rate_limits")
    op.drop_table("user_access")
