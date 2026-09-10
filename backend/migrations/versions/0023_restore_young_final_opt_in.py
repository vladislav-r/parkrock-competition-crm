"""Restore explicit opt-in for the 7-9 final without deleting existing results."""
from alembic import op

revision = "0023_young_final_opt_in"
down_revision = "0022_judge_conflicts"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE events SET version = version + 1
        WHERE id IN (SELECT event_id FROM age_groups
                     WHERE min_age = 7 AND max_age = 9 AND participates_in_final)
    """)
    op.execute("""
        UPDATE age_groups SET participates_in_final = false, version = version + 1
        WHERE min_age = 7 AND max_age = 9 AND participates_in_final
    """)


def downgrade():
    # Participation is a user choice; downgrading must not opt children in.
    pass
