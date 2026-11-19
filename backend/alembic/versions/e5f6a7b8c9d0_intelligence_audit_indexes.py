"""indexes for the audit log and merchant statistics

audit_logs is read newest-first with an optional action filter, and merchant risk groups
transactions by merchant_id; without these the database scans and sorts the whole table.
"""
from alembic import op

revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('ix_audit_logs_created_at_id', 'audit_logs', ['created_at', 'id'])
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'])
    op.create_index('ix_transactions_merchant_id', 'transactions', ['merchant_id'])


def downgrade():
    op.drop_index('ix_transactions_merchant_id', table_name='transactions')
    op.drop_index('ix_audit_logs_action', table_name='audit_logs')
    op.drop_index('ix_audit_logs_created_at_id', table_name='audit_logs')
