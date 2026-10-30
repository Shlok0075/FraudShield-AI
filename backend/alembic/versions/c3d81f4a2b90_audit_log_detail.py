"""add audit_logs.detail for auth events

Records which email was attempted on a login and, for a failed login, why it
was rejected. Without this the login trail only showed successful
`auth.login` rows, so repeated failed attempts (the thing an investigator
actually looks for) left no trace at all.

Revision ID: c3d81f4a2b90
Revises: 9b2c7e4a1f20
"""
from alembic import op
import sqlalchemy as sa

revision = "c3d81f4a2b90"
down_revision = "9b2c7e4a1f20"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("audit_logs", sa.Column("detail", sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column("audit_logs", "detail")
