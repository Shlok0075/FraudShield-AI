"""add graph_score to fraud_predictions"""
from alembic import op
import sqlalchemy as sa

revision = 'graph_score_v1'
down_revision = '9b2c7e4a1f20'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('fraud_predictions', sa.Column('graph_score', sa.Float(), nullable=True))

def downgrade():
    op.drop_column('fraud_predictions', 'graph_score')
