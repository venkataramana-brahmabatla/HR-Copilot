import logging
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_audit_log import AIAuditLog
from app.models.employee import Employee

logger = logging.getLogger(__name__)

_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_BEARER_PATTERN = re.compile(r"\bBearer\s+\S+", re.IGNORECASE)
_PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d .()-]{8,}\d)(?!\w)")
_FREE_TEXT_DETAIL_PATTERN = re.compile(r"\b(reason|description)\s*(?:is|:)?\s*.+$", re.IGNORECASE)
_BECAUSE_PATTERN = re.compile(r"\bbecause\b.+$", re.IGNORECASE)
_SENSITIVE_ARGUMENT_KEYS = {
    "reason",
    "description",
    "email",
    "phone",
    "address",
    "salary",
    "bank_account_number",
    "pan_number",
    "password",
    "token",
}


def _sanitize_text(value: str, *, limit: int = 4000) -> str:
    sanitized = _BEARER_PATTERN.sub("[REDACTED_TOKEN]", value)
    sanitized = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", sanitized)
    sanitized = _PHONE_PATTERN.sub("[REDACTED_PHONE]", sanitized)
    sanitized = _FREE_TEXT_DETAIL_PATTERN.sub(lambda match: f"{match.group(1)} [REDACTED]", sanitized)
    sanitized = _BECAUSE_PATTERN.sub("because [REDACTED]", sanitized)
    return sanitized[:limit]


def sanitize_tool_arguments(arguments: Any) -> Any:
    if isinstance(arguments, dict):
        safe_arguments = {}
        for key, value in arguments.items():
            if str(key).casefold() in _SENSITIVE_ARGUMENT_KEYS:
                safe_arguments[key] = "[REDACTED]" if value is not None else None
            else:
                safe_arguments[key] = sanitize_tool_arguments(value)
        return safe_arguments
    if isinstance(arguments, list):
        return [sanitize_tool_arguments(value) for value in arguments]
    if isinstance(arguments, str):
        return _sanitize_text(arguments, limit=500)
    return arguments


async def record_ai_audit(
    db: AsyncSession,
    *,
    current_user: Employee,
    message: str,
    intent: str | None,
    agent: str,
    status: str,
    session_id: str | None = None,
    tool_name: str | None = None,
    tool_arguments: dict | None = None,
    error_code: str | None = None,
    generated_sql: str | None = None,
    sql_validation_status: str | None = None,
    sql_execution_status: str | None = None,
) -> None:
    """Persist a minimal, redacted audit entry without failing the chat request."""
    db.add(
        AIAuditLog(
            user_id=current_user.id,
            role=getattr(current_user.role, "value", str(current_user.role)),
            session_id=session_id,
            message=_sanitize_text(message),
            intent=intent,
            agent=agent,
            tool_name=tool_name,
            tool_arguments=sanitize_tool_arguments(tool_arguments) if tool_arguments is not None else None,
            status=status,
            error_code=error_code,
            generated_sql=_sanitize_text(generated_sql) if generated_sql else None,
            sql_validation_status=sql_validation_status,
            sql_execution_status=sql_execution_status,
        )
    )
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception("Could not persist AI audit record", extra={"user_id": current_user.id, "agent": agent})
