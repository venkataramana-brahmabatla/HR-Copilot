import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.ai.agents.router import Intent, classify_intent, run_orchestrator


class RouterActionFollowUpTests(unittest.IsolatedAsyncioTestCase):
    async def test_bare_policy_prompt_asks_for_topic_without_calling_model(self):
        user = SimpleNamespace(id=1)
        with patch("app.ai.agents.router.llm_client.generate", new_callable=AsyncMock) as generate:
            intent = await classify_intent("policy")
            response = await run_orchestrator("policy", user, object())

        self.assertEqual(intent, Intent.UNKNOWN)
        self.assertEqual(response["answer"], "Which HR policy are you looking for? I can help with leave, attendance, work from home, travel, and other topics.")
        generate.assert_not_awaited()

    async def test_leave_policy_and_yearly_entitlement_questions_route_to_policy(self):
        for question in ("leave policy for employees", "leave policy", "total employee leaves per year"):
            with self.subTest(question=question), patch(
                "app.ai.agents.router.llm_client.generate",
                new_callable=AsyncMock,
            ) as generate:
                intent = await classify_intent(question)

            self.assertEqual(intent, Intent.POLICY)
            generate.assert_not_awaited()

    async def test_personal_leave_balance_question_keeps_normal_routing(self):
        with patch(
            "app.ai.agents.router.llm_client.generate",
            new_callable=AsyncMock,
            return_value='{"intent":"ACTION"}',
        ) as generate:
            intent = await classify_intent("How much leave do I have per year?")

        self.assertEqual(intent, Intent.ACTION)
        generate.assert_awaited_once()

    async def test_leave_reason_reply_remains_on_action_route(self):
        user = SimpleNamespace(id=7)
        db = object()
        history = [
            {"role": "user", "content": "Create a leave request for tomorrow"},
            {
                "role": "assistant",
                "content": "Which leave type would you like? Please provide a reason for the leave.",
            },
            {"role": "user", "content": "casual"},
            {
                "role": "assistant",
                "content": "Could you please provide a brief reason for the leave?",
            },
        ]
        with (
            patch("app.ai.agents.router.classify_intent", new_callable=AsyncMock) as classify,
            patch(
                "app.ai.agents.router.run_action",
                new_callable=AsyncMock,
                return_value={"intent": "ACTION", "answer": "Leave request submitted."},
            ) as action,
        ):
            result = await run_orchestrator("travelling", user, db, history=history)

        self.assertEqual(result["intent"], Intent.ACTION.value)
        classify.assert_not_awaited()
        action.assert_awaited_once_with("travelling", user, db, history=history)

    async def test_new_question_is_still_classified_normally_during_pending_action(self):
        user = SimpleNamespace(id=7)
        db = object()
        history = [
            {"role": "user", "content": "Create a leave request for tomorrow"},
            {"role": "assistant", "content": "Please provide a reason for the leave."},
        ]
        with (
            patch(
                "app.ai.agents.router.classify_intent",
                new_callable=AsyncMock,
                return_value=Intent.SQL,
            ) as classify,
            patch(
                "app.ai.agents.router.answer_sql_question",
                new_callable=AsyncMock,
                return_value={"summary": "Python-skilled employees: 3", "sql": "SELECT 1"},
            ) as sql,
        ):
            result = await run_orchestrator("Which employees know Python?", user, db, history=history)

        classify.assert_awaited_once()
        sql.assert_awaited_once()
        self.assertEqual(result["intent"], Intent.SQL.value)
