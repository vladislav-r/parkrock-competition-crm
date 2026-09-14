"""Allow named custom roles, keeping existing users and permission rows."""
from alembic import op
import sqlalchemy as sa

revision = "0026_custom_roles"
down_revision = "0025_team_quota"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("admins", "role_permissions"):
        op.alter_column(table, "role", type_=sa.String(50), postgresql_using="role::text")


def downgrade():
    # PostgreSQL refuses this conversion while custom roles exist, preserving data.
    for table in ("admins", "role_permissions"):
        op.alter_column(table, "role", type_=sa.Enum(name="userrole"), postgresql_using="role::userrole")
