"""One team quota for every category and both stages."""
from alembic import op
import sqlalchemy as sa

revision = "0025_team_quota"
down_revision = "0024_public_refresh"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("events", sa.Column("team_quota", sa.Integer(), nullable=False, server_default="2"))
    op.create_check_constraint("ck_events_team_quota", "events", "team_quota BETWEEN 1 AND 1000")


def downgrade():
    op.drop_constraint("ck_events_team_quota", "events", type_="check")
    op.drop_column("events", "team_quota")
