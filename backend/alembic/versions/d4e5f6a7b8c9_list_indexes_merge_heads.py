"""index alert/case sort columns; merge the two migration heads

The alerts and cases lists sort by created_at / updated_at; without an index the database
sorts the whole table on every page load.

This also merges `c3d81f4a2b90` and `graph_score_v1`, which both descended from `9b2c7e4a1f20`.
With two heads, `alembic upgrade head` (the Dockerfile's start command) refuses to run with
"Multiple head revisions are present".
"""
from alembic import op

revision = 'd4e5f6a7b8c9'
down_revision = ('c3d81f4a2b90', 'graph_score_v1')
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('ix_fraud_alerts_created_at', 'fraud_alerts', ['created_at'])
    op.create_index('ix_fraud_cases_updated_at', 'fraud_cases', ['updated_at'])


def downgrade():
    op.drop_index('ix_fraud_cases_updated_at', table_name='fraud_cases')
    op.drop_index('ix_fraud_alerts_created_at', table_name='fraud_alerts')
