from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agents.action_agent import run_action
from app.ai.agents.policy_agent import answer_policy_question
from app.ai.agents.router import run_orchestrator
from app.ai.agents.sql_agent import SQLExecutionError, answer_sql_question
from app.ai.llm import (
    LLMError,
    LLMConfigurationError,
    LLMTimeoutError,
    llm_client,
)
from app.ai.sql.guardrails import SQLValidationError
from app.core.response import error_response, success_response
from app.db.session import get_db
from app.models.ai_audit_log import AIAuditLog
from app.models.enums import Role
from app.models.hr_policy import HRPolicy
from app.models.employee import Employee
from app.schemas.chat import ActionChatRequest, ChatMessageCreate, ChatSessionCreate, ChatTestRequest, PolicyChatRequest, RouterChatRequest, SQLChatRequest
from app.services.ai_audit import record_ai_audit
from app.services.auth import get_current_user, require_roles

router = APIRouter()


async def _audit(
    db: AsyncSession,
    current_user: Employee,
    message: str,
    *,
    intent: str | None,
    agent: str,
    status_value: str,
    session_id: str | None = None,
    error_code: str | None = None,
    tool_name: str | None = None,
    tool_arguments: dict | None = None,
    generated_sql: str | None = None,
    sql_validation_status: str | None = None,
    sql_execution_status: str | None = None,
) -> None:
    await record_ai_audit(
        db,
        current_user=current_user,
        message=message,
        intent=intent,
        agent=agent,
        status=status_value,
        session_id=session_id,
        error_code=error_code,
        tool_name=tool_name,
        tool_arguments=tool_arguments,
        generated_sql=generated_sql,
        sql_validation_status=sql_validation_status,
        sql_execution_status=sql_execution_status,
    )


def _llm_status(exc: LLMError) -> str:
    if isinstance(exc, LLMConfigurationError):
        return "NOT_CONFIGURED"
    if isinstance(exc, LLMTimeoutError):
        return "TIMEOUT"
    return "PROVIDER_ERROR"


def _llm_error_response(exc: LLMError) -> JSONResponse:
    if isinstance(exc, LLMConfigurationError):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=error_response("LLM_NOT_CONFIGURED", "Set GROQ_API_KEY in backend/.env to enable model responses"),
        )
    if isinstance(exc, LLMTimeoutError):
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content=error_response("LLM_TIMEOUT", "The model provider did not respond in time"),
        )
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content=error_response("LLM_PROVIDER_ERROR", "The model provider could not complete the request"),
    )


@router.post("/test")
async def test_chat_completion(
    payload: ChatTestRequest,
    current_user: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        answer = await llm_client.generate([{"role": "user", "content": payload.message}])
    except LLMError as exc:
        await _audit(
            db, current_user, payload.message,
            intent=None, agent="llm_test", status_value=_llm_status(exc), error_code=type(exc).__name__.upper(),
        )
        return _llm_error_response(exc)

    await _audit(
        db, current_user, payload.message,
        intent=None, agent="llm_test", status_value="SUCCESS",
    )
    return success_response({"answer": answer})


@router.post("/policy")
async def chat_about_policy(
    payload: PolicyChatRequest,
    current_user: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    policies = (await db.execute(select(HRPolicy).order_by(HRPolicy.id.asc()))).scalars().all()
    try:
        answer = await answer_policy_question(payload.question, policies)
    except LLMError as exc:
        await _audit(
            db, current_user, payload.question,
            intent="POLICY", agent="policy_agent", status_value=_llm_status(exc),
            error_code=type(exc).__name__.upper(),
        )
        return _llm_error_response(exc)
    await _audit(db, current_user, payload.question, intent="POLICY", agent="policy_agent", status_value="SUCCESS")
    return success_response(answer)


@router.post("/sql")
async def chat_about_hr_data(
    payload: SQLChatRequest,
    current_user: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        answer = await answer_sql_question(payload.question, current_user, db)
    except LLMError as exc:
        await _audit(
            db, current_user, payload.question,
            intent="SQL", agent="sql_agent", status_value=_llm_status(exc), error_code=type(exc).__name__.upper(),
        )
        return _llm_error_response(exc)
    except SQLValidationError as exc:
        await _audit(
            db, current_user, payload.question,
            intent="SQL", agent="sql_agent", status_value="REJECTED", error_code="SQL_QUERY_REJECTED",
            generated_sql=getattr(exc, "generated_sql", None), sql_validation_status="REJECTED",
            sql_execution_status="NOT_RUN",
        )
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=error_response("SQL_QUERY_REJECTED", "The requested data query is not allowed"),
        )
    except SQLExecutionError as exc:
        await _audit(
            db, current_user, payload.question,
            intent="SQL", agent="sql_agent", status_value="ERROR", error_code="SQL_QUERY_FAILED",
            generated_sql=getattr(exc, "generated_sql", None),
            sql_validation_status=getattr(exc, "validation_status", None), sql_execution_status="FAILED",
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response("SQL_QUERY_FAILED", "The validated data query could not be completed"),
        )
    await _audit(
        db, current_user, payload.question, intent="SQL", agent="sql_agent", status_value="SUCCESS",
        generated_sql=answer.get("sql"), sql_validation_status="PASSED", sql_execution_status="SUCCEEDED",
    )
    return success_response(answer)


@router.post("/action")
async def chat_about_hr_actions(
    payload: ActionChatRequest,
    current_user: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        answer = await run_action(payload.question, current_user, db)
    except LLMError as exc:
        await _audit(
            db, current_user, payload.question,
            intent="ACTION", agent="action_agent", status_value=_llm_status(exc), error_code=type(exc).__name__.upper(),
        )
        return _llm_error_response(exc)
    except HTTPException as exc:
        if isinstance(exc.detail, dict) and "success" in exc.detail:
            content = exc.detail
        else:
            content = error_response("HR_ACTION_FAILED", "The requested HR action could not be completed")
        await _audit(
            db, current_user, payload.question,
            intent="ACTION", agent="action_agent", status_value="DENIED" if exc.status_code == 403 else "ERROR",
            error_code=f"HTTP_{exc.status_code}",
        )
        return JSONResponse(status_code=exc.status_code, content=content)
    audit = answer.pop("_audit", {})
    await _audit(
        db, current_user, payload.question,
        intent="ACTION", agent=audit.get("agent", "action_agent"), status_value=audit.get("status", "SUCCESS"),
        tool_name=audit.get("tool_name"), tool_arguments=audit.get("tool_arguments"),
    )
    return success_response(answer)


@router.post("/router")
async def chat_with_hr_copilot(
    payload: RouterChatRequest,
    current_user: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Classify a message and dispatch it to the policy, SQL, or action agent."""
    try:
        answer = await run_orchestrator(
            payload.question,
            current_user,
            db,
            session_id=payload.session_id,
            history=[message.model_dump() for message in payload.history],
        )
    except LLMError as exc:
        await _audit(
            db, current_user, payload.question, intent=None, agent="router",
            status_value=_llm_status(exc), session_id=payload.session_id,
            error_code=type(exc).__name__.upper(),
        )
        return _llm_error_response(exc)
    except SQLValidationError as exc:
        await _audit(
            db, current_user, payload.question, intent="SQL", agent="sql_agent", status_value="REJECTED",
            session_id=payload.session_id, error_code="SQL_QUERY_REJECTED",
            generated_sql=getattr(exc, "generated_sql", None), sql_validation_status="REJECTED",
            sql_execution_status="NOT_RUN",
        )
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=error_response("SQL_QUERY_REJECTED", "The requested data query is not allowed"),
        )
    except SQLExecutionError as exc:
        await _audit(
            db, current_user, payload.question, intent="SQL", agent="sql_agent", status_value="ERROR",
            session_id=payload.session_id, error_code="SQL_QUERY_FAILED",
            generated_sql=getattr(exc, "generated_sql", None),
            sql_validation_status=getattr(exc, "validation_status", None), sql_execution_status="FAILED",
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response("SQL_QUERY_FAILED", "The validated data query could not be completed"),
        )
    except HTTPException as exc:
        if isinstance(exc.detail, dict) and "success" in exc.detail:
            content = exc.detail
        else:
            content = error_response("HR_ACTION_FAILED", "The requested HR action could not be completed")
        await _audit(
            db, current_user, payload.question, intent="ACTION", agent="action_agent",
            status_value="DENIED" if exc.status_code == 403 else "ERROR", session_id=payload.session_id,
            error_code=f"HTTP_{exc.status_code}",
        )
        return JSONResponse(status_code=exc.status_code, content=content)
    audit = answer.pop("_audit", {})
    result = answer.get("result")
    sql_result = result if isinstance(result, dict) and "sql" in result else {}
    await _audit(
        db, current_user, payload.question,
        intent=answer.get("intent"), agent=audit.get("agent", "router"),
        status_value=audit.get("status", "SUCCESS"), session_id=payload.session_id,
        tool_name=audit.get("tool_name"), tool_arguments=audit.get("tool_arguments"),
        error_code=audit.get("error_code"),
        generated_sql=audit.get("generated_sql") or sql_result.get("sql"),
        sql_validation_status=audit.get("sql_validation_status"),
        sql_execution_status=audit.get("sql_execution_status"),
    )
    return success_response(answer)


@router.get("/audit")
async def list_ai_audit_logs(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: Employee = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    _ = current_user
    rows = (
        await db.execute(
            select(AIAuditLog).order_by(desc(AIAuditLog.created_at), desc(AIAuditLog.id)).offset(offset).limit(limit)
        )
    ).scalars().all()
    return success_response([
        {
            "id": row.id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "user_id": row.user_id,
            "role": row.role,
            "session_id": row.session_id,
            "message": row.message,
            "intent": row.intent,
            "agent": row.agent,
            "tool_name": row.tool_name,
            "tool_arguments": row.tool_arguments,
            "status": row.status,
            "error_code": row.error_code,
            "generated_sql": row.generated_sql,
            "sql_validation_status": row.sql_validation_status,
            "sql_execution_status": row.sql_execution_status,
        }
        for row in rows
    ])


@router.post("/sessions")
async def create_chat_session(
    payload: ChatSessionCreate,
    current_user: Employee = Depends(get_current_user),
):
    _ = payload
    _ = current_user
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content=error_response("CHAT_NOT_IMPLEMENTED", "Chat session creation is a Phase-3 stub and not implemented yet"),
    )


@router.post("/sessions/{session_id}/messages")
async def post_chat_message(
    session_id: str,
    payload: ChatMessageCreate,
    current_user: Employee = Depends(get_current_user),
):
    _ = session_id
    _ = payload
    _ = current_user
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content=error_response("CHAT_NOT_IMPLEMENTED", "Chat messaging is a Phase-3 stub and not implemented yet"),
    )
