# AI audit logging

The chat endpoints persist an audit row in `ai_audit_logs` for successful requests, clarifications, denials, SQL guardrail rejections, and handled provider or execution failures. The row records the authenticated employee and role, session ID when available, redacted message, detected intent, selected agent and tool, sanitized tool arguments, status/error code, and SQL validation/execution details where applicable.

Free-text tool arguments such as leave reasons and ticket descriptions are replaced with `[REDACTED]`. Messages and generated SQL redact bearer tokens, email addresses, phone-like numbers, and text following explicit `reason`, `description`, or `because` markers. Audit logging does not store HR tool results.

Admins can inspect the most recent entries with `GET /api/v1/chat/audit?limit=100&offset=0`. This endpoint requires the `ADMIN` role and supports pagination (1–200 rows per request). Audit storage has no automatic retention or deletion policy yet; operators should include the table in their database retention plan.

Apply the database migration before using the audit endpoint:

```bash
cd HRMS-main/backend
alembic upgrade head
```
