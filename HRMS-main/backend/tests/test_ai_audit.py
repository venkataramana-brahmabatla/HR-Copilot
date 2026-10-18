import unittest
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models import Employee
from app.models.ai_audit_log import AIAuditLog
from app.models.enums import EmployeeStatus, Role
from app.services.ai_audit import record_ai_audit


class AIAuditTests(unittest.IsolatedAsyncioTestCase):
    async def test_audit_persists_redacted_request_and_arguments(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            async with session_factory() as db:
                user = Employee(
                    name="Audit Test Employee",
                    email="audit-test@example.test",
                    hashed_password="not-used",
                    role=Role.EMPLOYEE,
                    status=EmployeeStatus.ACTIVE,
                    joining_date=date(2024, 1, 1),
                )
                db.add(user)
                await db.commit()
                await db.refresh(user)

                await record_ai_audit(
                    db,
                    current_user=user,
                    message="Create a ticket for audit-test@example.test",
                    intent="ACTION",
                    agent="action_agent",
                    status="SUCCESS",
                    session_id="test-session",
                    tool_name="create_ticket",
                    tool_arguments={"priority": "HIGH", "description": "Battery is swollen"},
                )

                entry = (await db.execute(select(AIAuditLog))).scalar_one()
                self.assertEqual(entry.user_id, user.id)
                self.assertEqual(entry.role, "EMPLOYEE")
                self.assertEqual(entry.intent, "ACTION")
                self.assertEqual(entry.agent, "action_agent")
                self.assertEqual(entry.tool_name, "create_ticket")
                self.assertEqual(entry.status, "SUCCESS")
                self.assertIn("[REDACTED_EMAIL]", entry.message)
                self.assertEqual(entry.tool_arguments["priority"], "HIGH")
                self.assertEqual(entry.tool_arguments["description"], "[REDACTED]")
        finally:
            await engine.dispose()
