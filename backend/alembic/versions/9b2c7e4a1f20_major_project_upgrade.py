"""major project upgrade tables and model registry fields"""
from alembic import op
import sqlalchemy as sa

revision = '9b2c7e4a1f20'
down_revision = '7c9e4d2f3a11'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('model_versions', sa.Column('status', sa.String(length=20), nullable=False, server_default='production'))
    op.add_column('model_versions', sa.Column('dataset_version', sa.String(length=100), nullable=True))
    op.add_column('model_versions', sa.Column('feature_version', sa.String(length=100), nullable=True))
    op.add_column('model_versions', sa.Column('threshold', sa.Float(), nullable=True))
    op.add_column('model_versions', sa.Column('artifact_path', sa.String(length=500), nullable=True))
    op.create_table('fraud_cases',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('alert_id', sa.Integer(), sa.ForeignKey('fraud_alerts.id'), nullable=False, unique=True),
        sa.Column('assigned_to', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('status', sa.String(30), nullable=False, server_default='open'),
        sa.Column('priority', sa.String(20), nullable=False, server_default='medium'),
        sa.Column('decision', sa.String(30), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_fraud_cases_status','fraud_cases',['status'])
    op.create_index('ix_fraud_cases_assignee','fraud_cases',['assigned_to'])
    op.create_table('case_notes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('fraud_cases.id'), nullable=False),
        sa.Column('author_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('note', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_case_notes_case_id','case_notes',['case_id'])
    op.create_table('fraud_feedback',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('prediction_id', sa.Integer(), sa.ForeignKey('fraud_predictions.id'), nullable=False),
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('fraud_cases.id'), nullable=True),
        sa.Column('reviewer_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('label', sa.String(30), nullable=False),
        sa.Column('reason', sa.String(500), nullable=True),
        sa.Column('feature_snapshot', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_fraud_feedback_prediction_id','fraud_feedback',['prediction_id'])
    op.create_table('user_behavior_profiles',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('transaction_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('avg_amount', sa.Float(), nullable=False, server_default='0'),
        sa.Column('max_amount', sa.Float(), nullable=False, server_default='0'),
        sa.Column('avg_daily_transactions', sa.Float(), nullable=False, server_default='0'),
        sa.Column('fraud_rate', sa.Float(), nullable=False, server_default='0'),
        sa.Column('normal_hours', sa.JSON(), nullable=True),
        sa.Column('known_devices', sa.JSON(), nullable=True),
        sa.Column('common_merchants', sa.JSON(), nullable=True),
        sa.Column('common_locations', sa.JSON(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_user_profiles_user_id','user_behavior_profiles',['user_id'], unique=True)
    op.create_table('drift_snapshots',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('metric', sa.String(50), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_table('security_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('check_name', sa.String(100), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

def downgrade():
    for t in ['security_events','drift_snapshots']:
        op.drop_table(t)
    op.drop_index('ix_user_profiles_user_id', table_name='user_behavior_profiles')
    op.drop_table('user_behavior_profiles')
    op.drop_index('ix_fraud_feedback_prediction_id', table_name='fraud_feedback')
    op.drop_table('fraud_feedback')
    op.drop_index('ix_case_notes_case_id', table_name='case_notes')
    op.drop_table('case_notes')
    op.drop_index('ix_fraud_cases_assignee', table_name='fraud_cases')
    op.drop_index('ix_fraud_cases_status', table_name='fraud_cases')
    op.drop_table('fraud_cases')
    for c in ['artifact_path','threshold','feature_version','dataset_version','status']:
        op.drop_column('model_versions', c)
