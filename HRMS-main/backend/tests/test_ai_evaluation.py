"""Offline, repeatable evaluations for retrieval and safety behavior.

These cases deliberately evaluate deterministic application controls. LLM answer
quality still needs the live-provider checklist in docs/evaluation/report.md.
"""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.ai.agents.action_agent import _ApproveLeaveArguments, _build_action_tools
from app.ai.agents.policy_agent import INSUFFICIENT_POLICY_ANSWER, answer_policy_question
from app.ai.rag.retriever import retrieve_policy_chunks
from app.ai.sql.guardrails import SQLValidationError, validate_and_scope_sql
from app.models.enums import Role
from app.models.hr_policy import HRPolicy


POLICIES = [
    HRPolicy(id=index, title=title, category=title.split()[0].upper(), content=content)
    for index, (title, content) in enumerate(
        [
            ("Leave Policy", "Employees can avail casual, sick, and earned leave as per allocated balances."),
            ("Attendance Policy", "Clock-in should be completed before 9:30 AM on working days."),
            ("Travel Reimbursement", "Travel claims must be submitted within 15 days of return."),
            ("Incident Reporting", "Security incidents should be reported to IT within 1 hour."),
            ("Probation Policy", "Probation period is six months unless explicitly waived."),
            ("Grievance Policy", "Employees may raise grievances through HR ticket workflow."),
        ],
        start=1,
    )
]


class PolicyRetrievalEvaluationTests(unittest.IsolatedAsyncioTestCase):
    async def test_generic_leave_policy_question_uses_retrieved_policy_text(self):
        for question in ("leave policy for employees", "HR policy for leaves"):
            with self.subTest(question=question), patch(
                "app.ai.agents.policy_agent.llm_client.generate", new_callable=AsyncMock
            ) as generate:
                result = await answer_policy_question(
                    question,
                    POLICIES,
                    context_question=(
                        "Recent conversation: total employee count and employees joined this year. "
                        f"Current user request: {question}"
                    ),
                )

            self.assertEqual(
                result["answer"],
                "Employees can avail casual, sick, and earned leave as per allocated balances. "
                "(Leave Policy – Leave Policy)",
            )
            self.assertEqual(result["sources"][0]["policy"], "Leave Policy")
            generate.assert_not_awaited()

    async def test_yearly_leave_allocation_question_does_not_invent_a_number(self):
        with patch("app.ai.agents.policy_agent.llm_client.generate", new_callable=AsyncMock) as generate:
            result = await answer_policy_question("total employee leaves per year", POLICIES)

        self.assertIn("does not specify a yearly number", result["answer"])
        self.assertIn("allocated balances", result["answer"])
        self.assertEqual(result["sources"][0]["policy"], "Leave Policy")
        generate.assert_not_awaited()

    def test_known_answer_questions_retrieve_the_expected_policy(self):
        cases = [
            ("What time should I clock in?", "Attendance Policy"),
            ("How soon must I report a security incident?", "Incident Reporting"),
            ("When should I submit a travel claim?", "Travel Reimbursement"),
            ("How long is the probation period?", "Probation Policy"),
            ("How can I raise a grievance?", "Grievance Policy"),
            ("How many casual leave days do I get?", "Leave Policy"),
        ]
        for question, expected_policy in cases:
            with self.subTest(question=question):
                matches = retrieve_policy_chunks(question, POLICIES)
                self.assertTrue(matches, "expected at least one retrieved policy")
                self.assertEqual(matches[0].chunk.title, expected_policy)

    def test_unanswerable_question_has_no_retrieved_context(self):
        matches = retrieve_policy_chunks("What is the policy for employees working on Mars?", POLICIES)
        self.assertEqual(matches, [])

    async def test_unanswerable_question_returns_refusal_without_calling_the_model(self):
        with patch("app.ai.agents.policy_agent.llm_client.generate", new_callable=AsyncMock) as generate:
            result = await answer_policy_question(
                "What is the policy for employees working on Mars?", POLICIES
            )

        self.assertEqual(result, {"answer": INSUFFICIENT_POLICY_ANSWER, "sources": []})
        generate.assert_not_awaited()


class SQLSafetyEvaluationTests(unittest.TestCase):
    def test_read_only_analytics_prompts_validate_for_authorized_roles(self):
        cases = [
            ("ADMIN", "SELECT COUNT(id) AS employee_count FROM employees", "LIMIT 100"),
            (
                "ADMIN",
                "SELECT d.name, COUNT(e.id) AS employee_count FROM departments d "
                "JOIN employees e ON e.department_id = d.id GROUP BY d.name",
                "LIMIT 100",
            ),
            ("ADMIN", "SELECT name, status FROM projects WHERE status = 'ONGOING'", "LIMIT 100"),
            ("EMPLOYEE", "SELECT leave_type, remaining FROM leave_balances", "employee_id = :current_employee_id"),
        ]
        for role, sql, expected_fragment in cases:
            with self.subTest(role=role, sql=sql):
                validated = validate_and_scope_sql(sql, role, employee_id=27)
                self.assertIn(expected_fragment, validated.sql)
                if role == "EMPLOYEE":
                    self.assertEqual(validated.parameters, {"current_employee_id": 27})

    def test_dangerous_or_out_of_scope_prompts_are_rejected(self):
        cases = [
            ("ADMIN", "DELETE FROM employees"),
            ("ADMIN", "UPDATE employees SET role = 'ADMIN'"),
            ("ADMIN", "SELECT current_salary_usd FROM employees"),
            ("EMPLOYEE", "SELECT name FROM employees"),
            ("UNKNOWN_ROLE", "SELECT id FROM employees"),
        ]
        for role, sql in cases:
            with self.subTest(role=role, sql=sql), self.assertRaises(SQLValidationError):
                validate_and_scope_sql(sql, role, employee_id=27)

    def test_manager_query_is_scoped_to_direct_reports(self):
        validated = validate_and_scope_sql(
            "SELECT e.name FROM employees e WHERE e.status = 'ACTIVE'",
            Role.MANAGER,
            employee_id=9,
        )
        self.assertIn("e.manager_id = :current_employee_id", validated.sql)
        self.assertEqual(validated.parameters, {"current_employee_id": 9})


class ActionPermissionEvaluationTests(unittest.IsolatedAsyncioTestCase):
    async def test_employee_cannot_invoke_approve_leave_tool(self):
        employee = SimpleNamespace(id=27, role=Role.EMPLOYEE)
        approve = AsyncMock(side_effect=AssertionError("unauthorized action reached executor"))
        with patch(
            "app.ai.agents.action_agent._TOOL_DEFINITIONS",
            {"approve_leave": (_ApproveLeaveArguments, approve, "Approve leave.")},
        ):
            tools, calls = _build_action_tools("Approve leave request 5", employee, object())
            result = json.loads(await tools[0].ainvoke({"request_id": 5}))

        self.assertEqual(result["status"], "denied")
        self.assertEqual(calls[0]["status"], "denied")
        approve.assert_not_awaited()

    async def test_manager_may_reach_approval_workflow(self):
        manager = SimpleNamespace(id=9, role=Role.MANAGER)
        approve = AsyncMock(return_value={"success": True, "data": {"id": 5, "status": "APPROVED"}})
        with patch(
            "app.ai.agents.action_agent._TOOL_DEFINITIONS",
            {"approve_leave": (_ApproveLeaveArguments, approve, "Approve leave.")},
        ):
            tools, calls = _build_action_tools("Approve leave request 5", manager, object())
            result = json.loads(await tools[0].ainvoke({"request_id": 5}))

        self.assertEqual(result["status"], "success")
        self.assertEqual(calls[0]["status"], "success")
        approve.assert_awaited_once_with({"request_id": 5}, manager, unittest.mock.ANY)


if __name__ == "__main__":
    unittest.main()
