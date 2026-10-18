import unittest
from datetime import date
from unittest.mock import AsyncMock, patch

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.ai.agents.sql_agent import (
    answer_sql_question,
    is_company_employee_count_question,
    is_employee_joined_count_question,
)
from app.ai.sql.guardrails import SQLValidationError, validate_and_scope_sql
from app.ai.sql.schema import describe_schema
from app.models.employee import Employee
from app.models.enums import Role


class SQLGuardrailTests(unittest.TestCase):
    def test_employee_leave_phrase_is_not_misread_as_employee_count(self):
        self.assertTrue(is_company_employee_count_question("total employee count"))
        self.assertFalse(is_company_employee_count_question("total employee leaves per year"))
        self.assertFalse(is_company_employee_count_question("How many employees joined the company this year?"))
        self.assertFalse(is_company_employee_count_question("employee count joined this year"))
        self.assertTrue(is_employee_joined_count_question("employee count joined this year"))

    def test_schema_prompt_discloses_case_sensitive_enum_values(self):
        schema = describe_schema("ADMIN")
        self.assertIn("Enum values are case-sensitive", schema)
        self.assertIn("employees.status: ACTIVE, INACTIVE", schema)
        self.assertIn("leave_requests.status: PENDING, APPROVED, REJECTED", schema)

    def test_admin_query_is_limited_and_keeps_safe_columns(self):
        query = validate_and_scope_sql(
            "SELECT d.name, COUNT(*) AS employee_count FROM departments d "
            "JOIN employees e ON e.department_id = d.id GROUP BY d.name",
            "ADMIN",
            7,
        )
        self.assertIn("LIMIT 100", query.sql)
        self.assertEqual(query.parameters, {})

    def test_admin_date_count_query_allows_sqlite_year_extraction(self):
        query = validate_and_scope_sql(
            "SELECT COUNT(*) AS employee_count FROM employees "
            "WHERE strftime('%Y', employees.joining_date) = '2026'",
            "ADMIN",
            7,
        )
        self.assertIn("strftime", query.sql.lower())
        self.assertIn("joining_date", query.sql)

    def test_employee_query_is_scoped_to_authenticated_employee(self):
        query = validate_and_scope_sql(
            "SELECT leave_type, remaining FROM leave_balances WHERE leave_type = 'CASUAL'",
            "EMPLOYEE",
            42,
        )
        self.assertIn("employee_id = :current_employee_id", query.sql)
        self.assertEqual(query.parameters, {"current_employee_id": 42})

    def test_manager_query_is_scoped_to_direct_reports(self):
        query = validate_and_scope_sql(
            "SELECT e.name, s.name FROM employees e "
            "JOIN employee_skills es ON es.employee_id = e.id "
            "JOIN skills s ON s.id = es.skill_id",
            "MANAGER",
            9,
        )
        self.assertIn("e.manager_id = :current_employee_id", query.sql)
        self.assertIn("es.employee_id IN (SELECT id FROM employees WHERE manager_id = :current_employee_id)", query.sql)

    def test_sensitive_columns_are_rejected(self):
        with self.assertRaises(SQLValidationError):
            validate_and_scope_sql("SELECT current_salary_usd FROM employees", "ADMIN", 1)

    def test_mutations_and_multiple_statements_are_rejected(self):
        for sql in (
            "DELETE FROM employees",
            "SELECT id FROM employees; DROP TABLE employees",
        ):
            with self.subTest(sql=sql), self.assertRaises(SQLValidationError):
                validate_and_scope_sql(sql, "ADMIN", 1)

    def test_wildcards_and_subqueries_are_rejected(self):
        for sql in (
            "SELECT * FROM employees",
            "SELECT id FROM employees WHERE id IN (SELECT employee_id FROM leave_requests)",
        ):
            with self.subTest(sql=sql), self.assertRaises(SQLValidationError):
                validate_and_scope_sql(sql, "ADMIN", 1)

    def test_limit_is_capped(self):
        query = validate_and_scope_sql("SELECT name FROM departments LIMIT 5000", "ADMIN", 1)
        self.assertTrue(query.sql.endswith("LIMIT 100"))


class SQLAgentExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_employee_id_question_includes_the_returned_id_in_the_answer(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.connect() as connection:
            await connection.execute(text("CREATE TABLE employees (id INTEGER, name TEXT)"))
            await connection.execute(text("INSERT INTO employees VALUES (731, 'Adam Andrews')"))
            await connection.commit()
            session = AsyncSession(bind=connection, expire_on_commit=False)
            try:
                admin = Employee(id=1, role=Role.ADMIN)
                with patch(
                    "app.ai.agents.sql_agent.llm_client.generate",
                    new=AsyncMock(return_value=(
                        "SELECT id FROM employees WHERE name = 'Adam Andrews'"
                    )),
                ):
                    response = await answer_sql_question(
                        "What is the id number of employee Adam Andrews?",
                        admin,
                        session,
                    )

                self.assertEqual(response["result"], [{"id": 731}])
                self.assertEqual(response["summary"], "The employee ID is 731.")
            finally:
                await session.close()
        await engine.dispose()

    async def test_joined_employee_count_is_not_misread_as_active_headcount(self):
        current_year = date.today().year
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.connect() as connection:
            await connection.execute(text("CREATE TABLE employees (id INTEGER, status TEXT, joining_date TEXT)"))
            await connection.execute(text(
                "INSERT INTO employees VALUES "
                f"(1, 'ACTIVE', '{current_year}-01-02'), "
                f"(2, 'ACTIVE', '{current_year}-08-12'), "
                f"(3, 'INACTIVE', '{current_year - 1}-12-30')"
            ))
            await connection.commit()
            session = AsyncSession(bind=connection, expire_on_commit=False)
            try:
                admin = Employee(id=1, role=Role.ADMIN)
                with patch("app.ai.agents.sql_agent.llm_client.generate", new=AsyncMock()) as generate:
                    response = await answer_sql_question(
                        "employee count joined this year",
                        admin,
                        session,
                        context_question=(
                            "Recent conversation: User asked total employee count. "
                            "Current user request: employee count joined this year"
                        ),
                    )

                generate.assert_not_awaited()
                self.assertEqual(response["result"], [{"joined_employee_count": 2}])
                self.assertEqual(response["summary"], "2 employees joined this year.")
            finally:
                await session.close()
        await engine.dispose()

    async def test_employee_cannot_query_company_wide_employee_count(self):
        employee = Employee(id=2, role=Role.EMPLOYEE)
        with patch(
            "app.ai.agents.sql_agent.llm_client.generate",
            new=AsyncMock(),
        ) as generate:
            response = await answer_sql_question("total employee count", employee, None)

        generate.assert_not_awaited()
        self.assertEqual(response["status"], "DENIED")
        self.assertNotIn("sql", response)
        self.assertIn("company-wide", response["summary"])

    async def test_admin_employee_count_uses_active_employee_count_query(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.connect() as connection:
            await connection.execute(text("CREATE TABLE employees (id INTEGER, status TEXT)"))
            await connection.execute(text(
                "INSERT INTO employees VALUES (1, 'ACTIVE'), (2, 'ACTIVE'), (3, 'INACTIVE')"
            ))
            await connection.commit()
            session = AsyncSession(bind=connection, expire_on_commit=False)
            try:
                admin = Employee(id=1, role=Role.ADMIN)
                with patch(
                    "app.ai.agents.sql_agent.llm_client.generate",
                    new=AsyncMock(),
                ) as generate:
                    response = await answer_sql_question("total employee count", admin, session)

                generate.assert_not_awaited()
                self.assertEqual(response["result"], [{"active_employee_count": 2}])
                self.assertEqual(response["summary"], "There are 2 active employees.")
                self.assertIn("status = 'ACTIVE'", response["sql"])
            finally:
                await session.close()
        await engine.dispose()

    async def test_employee_query_returns_only_own_rows_and_resets_read_only_mode(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.connect() as connection:
            await connection.execute(text(
                "CREATE TABLE leave_balances (id INTEGER, employee_id INTEGER, leave_type TEXT, remaining REAL)"
            ))
            await connection.execute(text(
                "INSERT INTO leave_balances VALUES (1, 2, 'CASUAL', 8), (2, 3, 'CASUAL', 12)"
            ))
            await connection.commit()
            session = AsyncSession(bind=connection, expire_on_commit=False)
            try:
                employee = Employee(id=2, role=Role.EMPLOYEE)
                with patch(
                    "app.ai.agents.sql_agent.llm_client.generate",
                    new=AsyncMock(return_value="SELECT leave_type, remaining FROM leave_balances"),
                ):
                    response = await answer_sql_question("Show my leave balance", employee, session)

                self.assertEqual(response["result"], [{"leave_type": "CASUAL", "remaining": 8.0}])
                await session.execute(text(
                    "INSERT INTO leave_balances VALUES (3, 4, 'SICK', 4)"
                ))
                await session.rollback()
            finally:
                await session.close()
        await engine.dispose()

    async def test_manager_query_returns_only_direct_report_rows(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.connect() as connection:
            await connection.execute(text(
                "CREATE TABLE employees (id INTEGER, name TEXT, manager_id INTEGER, status TEXT)"
            ))
            await connection.execute(text(
                "INSERT INTO employees VALUES (1, 'Manager', NULL, 'ACTIVE'), "
                "(2, 'Direct Report', 1, 'ACTIVE'), (3, 'Other Employee', 9, 'ACTIVE')"
            ))
            await connection.commit()
            session = AsyncSession(bind=connection, expire_on_commit=False)
            try:
                manager = Employee(id=1, role=Role.MANAGER)
                with patch(
                    "app.ai.agents.sql_agent.llm_client.generate",
                    new=AsyncMock(return_value=(
                        "SELECT e.name FROM employees e WHERE e.status = 'ACTIVE' "
                        "OR e.name = 'Other Employee'"
                    )),
                ):
                    response = await answer_sql_question("List my team", manager, session)

                self.assertEqual(response["result"], [{"name": "Direct Report"}])
            finally:
                await session.close()
        await engine.dispose()


if __name__ == "__main__":
    unittest.main()
