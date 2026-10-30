"""add hybrid fraud prediction signal fields

Revision ID: 7c9e4d2f3a11
Revises: 4af2b79611aa
"""
from alembic import op
import sqlalchemy as sa

revision = "7c9e4d2f3a11"
down_revision = "4af2b79611aa"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("fraud_predictions", sa.Column("decision", sa.String(length=20), nullable=True))
    op.add_column("fraud_predictions", sa.Column("anomaly_score", sa.Float(), nullable=True))
    op.add_column("fraud_predictions", sa.Column("behavior_score", sa.Float(), nullable=True))
    op.add_column("fraud_predictions", sa.Column("rule_score", sa.Float(), nullable=True))
    op.add_column("fraud_predictions", sa.Column("triggered_rules", sa.JSON(), nullable=True))
    op.add_column("fraud_predictions", sa.Column("reasons", sa.JSON(), nullable=True))
    op.add_column("fraud_predictions", sa.Column("signal_contributions", sa.JSON(), nullable=True))
    op.add_column("fraud_predictions", sa.Column("weights_used", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("fraud_predictions", "weights_used")
    op.drop_column("fraud_predictions", "signal_contributions")
    op.drop_column("fraud_predictions", "reasons")
    op.drop_column("fraud_predictions", "triggered_rules")
    op.drop_column("fraud_predictions", "rule_score")
    op.drop_column("fraud_predictions", "behavior_score")
    op.drop_column("fraud_predictions", "anomaly_score")
    op.drop_column("fraud_predictions", "decision")
