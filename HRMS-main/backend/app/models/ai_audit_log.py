from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AIAuditLog(Base):
    __tablename__ = "ai_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False, index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    agent: Mapped[str] = mapped_column(String(80), nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tool_arguments: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    generated_sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    sql_validation_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sql_execution_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
