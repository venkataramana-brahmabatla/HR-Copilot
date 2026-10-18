import json
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.ai.agents.action_agent import (
    _ApplyLeaveArguments,
    _CreateTicketArguments,
    _NoArguments,
    _build_action_tools,
    _build_model,
    run_action,
)
from app.core.response import success_response
from app.db.base import Base
from app.models import Employee, LeaveRequest, Ticket
from app.models.enums import EmployeeStatus, Role


class ActionAgentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user = SimpleNamespace(id=7, role=Role.EMPLOYEE)
        self.db = object()

    def test_model_uses_root_base_url_when_config_contains_openai_compatible_path(self):
        with (
            patch("app.ai.agents.action_agent.settings.groq_api_key", "test-key"),
            patch("app.ai.agents.action_agent.settings.llm_base_url", "https://api.groq.com/openai/v1/"),
            patch("app.ai.agents.action_agent.ChatGroq") as chat_groq,
        ):
            _build_model()

        self.assertEqual(chat_groq.call_args.kwargs["base_url"], "https://api.groq.com")

    def test_model_keeps_root_base_url_unchanged(self):
        with (
            patch("app.ai.agents.action_agent.settings.groq_api_key", "test-key"),
            patch("app.ai.agents.action_agent.settings.llm_base_url", "https://api.groq.com/"),
            patch("app.ai.agents.action_agent.ChatGroq") as chat_groq,
        ):
            _build_model()

        self.assertEqual(chat_groq.call_args.kwargs["base_url"], "https://api.groq.com")

    async def test_missing_leave_reason_never_executes_tool(self):
        apply_leave = AsyncMock()
        with patch("app.ai.agents.action_agent._TOOL_DEFINITIONS", {
            "apply_leave": (
                _ApplyLeaveArguments,
                apply_leave,
                "Submit leave.",
            )
        }):
            tools, called = _build_action_tools("Apply casual leave on Friday", self.user, self.db)
            output = await tools[0].ainvoke({
                "leave_type": "CASUAL",
                "start_date": "2026-10-16",
                "end_date": "2026-10-16",
                "reason": "doctor appointment",
            })

        self.assertEqual(json.loads(output)["status"], "needs_clarification")
        self.assertIn("reason for the leave", called[0]["result"]["message"])
        apply_leave.assert_not_awaited()

    @patch("app.ai.agents.action_agent.create_agent")
    async def test_balance_tool_uses_current_user_and_observed_result(self, create_agent):
        get_balance = AsyncMock(return_value=success_response(
            [{"leave_type": "CASUAL", "total": 12, "used": 4, "remaining": 8}]
        ))
        with patch.dict("app.ai.agents.action_agent._TOOL_DEFINITIONS", {
            "get_leave_balance": (_NoArguments,
                                  get_balance, "Read balances.")
        }):
            tools, called = _build_action_tools("How much casual leave do I have?", self.user, self.db)
            raw_result = await tools[0].ainvoke({})

        self.assertEqual(json.loads(raw_result)["status"], "success")
        self.assertEqual(called[0]["result"][0]["remaining"], 8)
        get_balance.assert_awaited_once_with({}, self.user, self.db)

        create_agent.return_value.ainvoke = AsyncMock(return_value={
            "messages": [AIMessage(content="Your balance is 8 days.")]
        })
        result = await run_action("How much casual leave do I have?", self.user, self.db)
        self.assertEqual(result["answer"], "Your balance is 8 days.")
        create_agent.assert_called_once()

    async def test_unrequested_ticket_details_do_not_execute(self):
        create_ticket = AsyncMock()
        with patch.dict("app.ai.agents.action_agent._TOOL_DEFINITIONS", {
            "create_ticket": (_CreateTicketArguments, create_ticket, "Create ticket.")
        }):
            tools, called = _build_action_tools("Create an IT ticket for my laptop", self.user, self.db)
            tool = next(tool for tool in tools if tool.name == "create_ticket")
            raw_result = await tool.ainvoke({
                "title": "Laptop setup",
                "description": "Configure laptop setup",
                "category": "IT",
                "priority": "MEDIUM",
            })

        self.assertEqual(json.loads(raw_result)["status"], "needs_clarification")
        self.assertIn("priority", called[0]["result"]["message"])
        create_ticket.assert_not_awaited()

    async def test_missing_ticket_details_are_requested_together(self):
        create_ticket = AsyncMock()
        with patch.dict("app.ai.agents.action_agent._TOOL_DEFINITIONS", {
            "create_ticket": (_CreateTicketArguments, create_ticket, "Create ticket.")
        }):
            tools, called = _build_action_tools("Create an IT ticket for my laptop", self.user, self.db)
            ticket_tool = next(tool for tool in tools if tool.name == "create_ticket")
            raw_result = await ticket_tool.ainvoke({"category": "IT"})

        result = json.loads(raw_result)
        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(
            result["message"],
            "To create your ticket, please provide ticket priority (low, medium, or high), ticket title, ticket description.",
        )
        self.assertEqual(called[0]["status"], "needs_clarification")
        create_ticket.assert_not_awaited()

    @patch("app.ai.agents.action_agent.create_agent")
    async def test_ticket_follow_up_reuses_details_from_prior_user_turns(self, create_agent):
        history = [
            {"role": "user", "content": "Create an IT ticket for my laptop issue"},
            {"role": "assistant", "content": "Please provide the ticket priority, title, and description."},
        ]
        create_ticket = AsyncMock(return_value=success_response({
            "id": 11,
            "category": "IT",
            "status": "OPEN",
        }))

        async def invoke_agent(payload, config):
            self.assertEqual(payload["messages"][:2], history)
            ticket_tool = next(tool for tool in payload_tools if tool.name == "create_ticket")
            await ticket_tool.ainvoke({
                "category": "IT",
                "priority": "HIGH",
                "title": "laptop battery issues",
                "description": "battery drained",
            })
            return {"messages": []}

        def create_agent_with_tools(*, tools, **kwargs):
            nonlocal payload_tools
            payload_tools = tools
            return SimpleNamespace(ainvoke=invoke_agent)

        payload_tools = []
        create_agent.side_effect = create_agent_with_tools
        with (
            patch("app.ai.agents.action_agent._build_model", return_value=object()),
            patch.dict("app.ai.agents.action_agent._TOOL_DEFINITIONS", {
                "create_ticket": (_CreateTicketArguments, create_ticket, "Create ticket.")
            }),
        ):
            result = await run_action(
                "high, laptop battery issues, drained",
                self.user,
                self.db,
                history=history,
            )

        self.assertEqual(result["tool"]["status"], "success")
        self.assertIn("ticket #11 was created", result["answer"])
        create_ticket.assert_awaited_once()

    async def test_only_one_tool_can_execute_per_request(self):
        get_balance = AsyncMock(return_value=success_response([]))
        create_ticket = AsyncMock()
        with patch.dict("app.ai.agents.action_agent._TOOL_DEFINITIONS", {
            "get_leave_balance": (_NoArguments, get_balance, "Read balances."),
            "create_ticket": (_CreateTicketArguments, create_ticket, "Create ticket."),
        }):
            tools, _ = _build_action_tools("Check leave and create a ticket", self.user, self.db)
            balance_tool = next(tool for tool in tools if tool.name == "get_leave_balance")
            ticket_tool = next(tool for tool in tools if tool.name == "create_ticket")
            first = json.loads(await balance_tool.ainvoke({}))
            second = json.loads(await ticket_tool.ainvoke({
                "title": "Laptop setup",
                "description": "Laptop cannot start",
                "category": "IT",
                "priority": "HIGH",
            }))

        self.assertEqual(first["status"], "success")
        self.assertEqual(second["status"], "blocked")
        create_ticket.assert_not_awaited()

    async def test_leave_and_ticket_tools_persist_through_existing_hr_workflows(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            async with session_factory() as db:
                user = Employee(
                    name="Action Test Employee",
                    email="action-test@example.test",
                    hashed_password="not-used",
                    role=Role.EMPLOYEE,
                    status=EmployeeStatus.ACTIVE,
                    joining_date=date(2024, 1, 1),
                )
                db.add(user)
                await db.commit()
                await db.refresh(user)

                tools, leave_calls = _build_action_tools(
                    "Apply casual leave on 2026-11-02 because of my doctor appointment.", user, db
                )
                await tools[2].ainvoke({
                    "leave_type": "CASUAL",
                    "start_date": "2026-11-02",
                    "end_date": "2026-11-02",
                    "reason": "doctor appointment",
                })
                leave = (await db.execute(select(LeaveRequest))).scalar_one()
                self.assertEqual(leave_calls[0]["status"], "success")
                self.assertEqual(leave.status.value, "PENDING")

                ticket_tools, ticket_calls = _build_action_tools(
                    "Create a high priority IT ticket titled Laptop setup with description Laptop cannot start.",
                    user,
                    db,
                )
                await ticket_tools[3].ainvoke({
                    "title": "Laptop setup",
                    "description": "Laptop cannot start",
                    "category": "IT",
                    "priority": "HIGH",
                })
                ticket = (await db.execute(select(Ticket))).scalar_one()
                self.assertEqual(ticket_calls[0]["status"], "success")
                self.assertEqual(ticket.employee_id, user.id)
                self.assertEqual(ticket.title, "Laptop setup")
        finally:
            await engine.dispose()


if __name__ == "__main__":
    unittest.main()
