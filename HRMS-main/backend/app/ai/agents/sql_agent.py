import re
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm import llm_client
from app.ai.sql.guardrails import MAX_RESULT_ROWS, SQLValidationError, validate_and_scope_sql
from app.ai.sql.schema import SUPPORTED_ROLES, describe_schema, role_name
from app.models.employee import Employee

_EMPLOYEE_COUNT_PATTERNS = (
    re.compile(r"\b(?:total|overall|active)\s+(?:number of\s+)?(?:employees?|staff|people|workers?|team members?)\s+(?:headcount|count)\b", re.IGNORECASE),
    re.compile(r"\b(?:employee|employees|staff|workforce)\s+(?:headcount|count|total)\b", re.IGNORECASE),
    re.compile(r"\b(?:total|overall|active)\s+(?:number of\s+)?(?:employees?|staff|people|workers?|team members?)\s*[?.!]*$", re.IGNORECASE),
    re.compile(r"\b(?:how many|count of|number of|total number of)\s+(?:active\s+)?(?:employees?|staff|people|workers?|team members?)(?:\s+(?:are there|in total|overall))?\s*[?.!]*$", re.IGNORECASE),
    re.compile(r"\bheadcount\b|\b(?:company|organization|organisation|org)\s+size\b", re.IGNORECASE),
)
_EMPLOYEE_TERMS = re.compile(r"\b(?:employees?|staff|workers?|people)\b", re.IGNORECASE)
_JOIN_TERMS = re.compile(r"\b(?:joined|hired|onboarded|started)\b", re.IGNORECASE)
_COUNT_TERMS = re.compile(r"\b(?:count|number|how many|total)\b", re.IGNORECASE)


def is_employee_joined_count_question(question: str) -> bool:
    return bool(
        _EMPLOYEE_TERMS.search(question)
        and _JOIN_TERMS.search(question)
        and _COUNT_TERMS.search(question)
    )


def is_company_employee_count_question(question: str) -> bool:
    # A count of hires is a different intent from the current workforce headcount.
    if is_employee_joined_count_question(question):
        return False
    return any(pattern.search(question) for pattern in _EMPLOYEE_COUNT_PATTERNS)


class SQLAgentError(Exception):
    """Base error raised while processing a natural-language SQL question."""


class SQLExecutionError(SQLAgentError):
    def __init__(self, message: str, *, generated_sql: str | None = None, validation_status: str | None = None):
        super().__init__(message)
        self.generated_sql = generated_sql
        self.validation_status = validation_status


async def answer_sql_question(
    question: str,
    current_user: Employee,
    db: AsyncSession,
    *,
    context_question: str | None = None,
) -> dict:
    role = current_user.role
    current_role = role_name(role)
    if current_role not in SUPPORTED_ROLES:
        raise SQLValidationError("The authenticated role is not allowed to query HR data")
    is_joined_count = is_employee_joined_count_question(question)
    is_employee_count = is_company_employee_count_question(question)

    if is_employee_count and current_role != "ADMIN":
        if current_role == "MANAGER":
            summary = "Only admins can view company-wide employee counts. I can help with questions about your team."
        else:
            summary = "I can’t provide company-wide employee counts for your account. I can help with your own leave data."
        return {"question": question, "result": [], "summary": summary, "status": "DENIED"}

    if is_joined_count and current_role == "EMPLOYEE":
        return {
            "question": question,
            "result": [],
            "summary": "I can’t provide company-wide hiring counts for your account.",
            "status": "DENIED",
        }

    if is_joined_count:
        current_year = date.today().year
        query_sql = (
            "SELECT COUNT(*) AS joined_employee_count FROM employees "
            f"WHERE strftime('%Y', joining_date) = '{current_year}'"
        )
    elif is_employee_count:
        query_sql = "SELECT COUNT(*) AS active_employee_count FROM employees WHERE status = 'ACTIVE'"
    else:
        messages = [
            {
                "role": "system",
                "content": (
                    "Translate the user's HR analytics question into one SQLite SELECT statement. "
                    "Return SQL only, with no markdown or explanation. Use only the supplied schema. "
                    f"The current date is {date.today().isoformat()}; resolve relative dates such as 'this year' from it. "
                    "If recent conversation is included, answer only the current user request; use older messages only "
                    "to resolve references and never repeat an earlier query. "
                    "Never request salary, bank, tax, authentication, contact, address, birth-date, or document data. "
                    "The backend validates and scopes your SQL; do not attempt to bypass those controls.\n\n"
                    f"{describe_schema(role)}"
                ),
            },
            {"role": "user", "content": context_question or question},
        ]
        generated_sql = await llm_client.generate(messages)
        query_sql = _remove_code_fence(generated_sql)
    try:
        validated = validate_and_scope_sql(query_sql, role, current_user.id)
    except SQLValidationError as exc:
        raise SQLValidationError(str(exc), generated_sql=query_sql) from exc

    if not db.bind or db.bind.dialect.name != "sqlite":
        raise SQLExecutionError(
            "The safe SQL executor currently supports SQLite only",
            generated_sql=validated.sql,
            validation_status="PASSED",
        )

    try:
        await db.execute(text("PRAGMA query_only = ON"))
        result = await db.execute(text(validated.sql), validated.parameters)
        rows = [
            {key: _json_value(value) for key, value in row.items()}
            for row in result.mappings().fetchmany(MAX_RESULT_ROWS)
        ]
    except Exception as exc:
        raise SQLExecutionError(
            "The validated query could not be executed",
            generated_sql=validated.sql,
            validation_status="PASSED",
        ) from exc
    finally:
        try:
            await db.execute(text("PRAGMA query_only = OFF"))
        except Exception:
            await db.rollback()

    count = len(rows)
    if is_employee_count:
        employee_count = rows[0]["active_employee_count"] if rows else 0
        summary = f"There are {employee_count} active employees."
    elif is_joined_count:
        joined_count = rows[0]["joined_employee_count"] if rows else 0
        if current_role == "MANAGER":
            summary = f"{joined_count} of your direct reports joined this year."
        else:
            summary = f"{joined_count} employees joined this year."
    elif rows and re.search(r"\bCOUNT\s*\(", validated.sql, re.IGNORECASE) and len(rows[0]) == 1:
        count_value = next(iter(rows[0].values()))
        if re.search(r"\b(?:employees?|staff)\b.{0,50}\b(?:joined|hired)\b", question, re.IGNORECASE):
            period = "this year" if re.search(r"\bthis year\b", question, re.IGNORECASE) else "during the requested period"
            if current_role == "MANAGER":
                summary = f"{count_value} of your direct reports joined {period}."
            else:
                summary = f"{count_value} employees joined {period}."
        else:
            summary = f"The count is {count_value}."
    elif rows:
        summary = _summarize_rows(question, rows)
    elif count == 0:
        summary = "The query returned no matching records."
    elif count == 1:
        summary = "The query returned one matching record."
    else:
        summary = f"The query returned {count} rows (maximum {MAX_RESULT_ROWS})."

    return {
        "question": question,
        "sql": validated.sql,
        "result": rows,
        "summary": summary,
        "status": "SUCCESS",
    }


def _remove_code_fence(sql: str) -> str:
    cleaned = sql.strip()
    cleaned = re.sub(r"^```(?:sql)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Enum):
        return value.value
    return value


def _summarize_rows(question: str, rows: list[dict]) -> str:
    if len(rows) == 1:
        row = rows[0]
        if re.search(r"\b(?:employee\s+(?:id|number)|id\s+number)\b", question, re.IGNORECASE):
            for key, value in row.items():
                if key.lower() in {"id", "employee_id", "employee_number", "employee_no"}:
                    return f"The employee ID is {value}."
        details = "; ".join(f"{_display_column(key)}: {value}" for key, value in row.items())
        return f"I found one matching record: {details}."

    visible_rows = rows[:10]
    formatted_rows = [
        ", ".join(f"{_display_column(key)}: {value}" for key, value in row.items())
        for row in visible_rows
    ]
    summary = "Here are the matching records: " + "; ".join(formatted_rows) + "."
    if len(rows) > len(visible_rows):
        summary += f" Showing the first {len(visible_rows)} results."
    return summary


def _display_column(name: str) -> str:
    return name.replace("_", " ").strip().capitalize()
