"""add AI audit logs

Revision ID: 0017_ai_audit_logs
Revises: 0016_employee_documents_uploaded_by
Create Date: 2026-10-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0017_ai_audit_logs"
down_revision: Union[str, None] = "0016_employee_documents_uploaded_by"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("session_id", sa.String(length=100), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(length=32), nullable=True),
        sa.Column("agent", sa.String(length=80), nullable=False),
        sa.Column("tool_name", sa.String(length=80), nullable=True),
        sa.Column("tool_arguments", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("generated_sql", sa.Text(), nullable=True),
        sa.Column("sql_validation_status", sa.String(length=32), nullable=True),
        sa.Column("sql_execution_status", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["employees.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_ai_audit_logs_created_at", "ai_audit_logs", ["created_at"])
    op.create_index("ix_ai_audit_logs_user_id", "ai_audit_logs", ["user_id"])
    op.create_index("ix_ai_audit_logs_session_id", "ai_audit_logs", ["session_id"])
    op.create_index("ix_ai_audit_logs_intent", "ai_audit_logs", ["intent"])
    op.create_index("ix_ai_audit_logs_status", "ai_audit_logs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_ai_audit_logs_status", table_name="ai_audit_logs")
    op.drop_index("ix_ai_audit_logs_intent", table_name="ai_audit_logs")
    op.drop_index("ix_ai_audit_logs_session_id", table_name="ai_audit_logs")
    op.drop_index("ix_ai_audit_logs_user_id", table_name="ai_audit_logs")
    op.drop_index("ix_ai_audit_logs_created_at", table_name="ai_audit_logs")
    op.drop_table("ai_audit_logs")
