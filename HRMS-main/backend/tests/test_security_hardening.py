import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException

from app.api.v1.endpoints.employees import get_employee
from app.core.config import Settings
from app.core.security import create_access_token, create_refresh_token, decode_access_token
from app.models.enums import Role
from app.services.uploads import read_upload_limited


class TokenTypeTests(unittest.TestCase):
    def test_access_token_is_accepted(self):
        token = create_access_token("12", "EMPLOYEE")
        self.assertEqual(decode_access_token(token)["sub"], "12")

    def test_refresh_token_is_not_accepted_as_access(self):
        token = create_refresh_token("12")
        with self.assertRaises(ValueError):
            decode_access_token(token)


class JwtConfigurationTests(unittest.TestCase):
    def test_production_requires_a_strong_jwt_secret(self):
        with self.assertRaises(ValueError):
            Settings(_env_file=None, environment="production", jwt_secret_key="")

    def test_development_generates_a_non_default_jwt_secret(self):
        settings = Settings(_env_file=None, environment="dev", jwt_secret_key="")
        self.assertGreaterEqual(len(settings.jwt_secret_key), 32)
        self.assertNotEqual(settings.jwt_secret_key, "change_me")


class UploadSizeTests(unittest.IsolatedAsyncioTestCase):
    async def test_upload_reader_stops_after_limit_plus_one_byte(self):
        limit = 128 * 1024
        upload = _FakeUpload(b"x" * (limit * 20))

        with self.assertRaises(HTTPException) as raised:
            await read_upload_limited(upload, limit)

        self.assertEqual(raised.exception.status_code, 413)
        self.assertEqual(upload.bytes_read, limit + 1)

    async def test_upload_reader_returns_small_file(self):
        upload = _FakeUpload(b"small file")
        self.assertEqual(await read_upload_limited(upload, 1024), b"small file")


class EmployeeDetailPrivacyTests(unittest.IsolatedAsyncioTestCase):
    async def test_non_admin_employee_detail_omits_sensitive_fields(self):
        response = await get_employee(
            22,
            current_user=SimpleNamespace(id=7, role=Role.EMPLOYEE),
            db=_employee_detail_db(),
        )

        self.assertEqual(response["success"], True)
        for sensitive_field in (
            "current_salary_usd",
            "bank_account_number",
            "pan_number",
            "date_of_birth",
            "address",
        ):
            self.assertNotIn(sensitive_field, response["data"])

    async def test_admin_employee_detail_keeps_admin_finance_fields(self):
        response = await get_employee(
            22,
            current_user=SimpleNamespace(id=1, role=Role.ADMIN),
            db=_employee_detail_db(),
        )
        self.assertIn("current_salary_usd", response["data"])
        self.assertIn("bank_account_number", response["data"])


class _FakeUpload:
    def __init__(self, content: bytes):
        self.content = content
        self.bytes_read = 0
        self.size = None

    async def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self.content) - self.bytes_read
        end = min(len(self.content), self.bytes_read + size)
        chunk = self.content[self.bytes_read:end]
        self.bytes_read = end
        return chunk


def _employee_detail_db():
    employee = SimpleNamespace(
        id=22,
        name="Example Employee",
        email="employee@example.test",
        phone="5555555555",
        role=Role.EMPLOYEE,
        status=SimpleNamespace(value="ACTIVE"),
        department_id=None,
        joining_date="2024-01-01",
        profile_photo_path=None,
        date_of_birth="1990-01-01",
        blood_type="O+",
        occupancy="Full-Time",
        address="Private address",
        current_salary_usd=123456,
        bank_name="Example Bank",
        bank_account_number="1234567890",
        bank_account_name="Example Employee",
        bank_branch="Main Branch",
        bank_ifsc="EXAMPLE001",
        pan_number="ABCDE1234F",
        pan_name="Example Employee",
        pan_dob="1990-01-01",
    )

    rows = []
    employee_result = MagicMock()
    employee_result.scalar_one_or_none.return_value = employee
    rows.append(employee_result)

    job_history_result = MagicMock()
    job_history_result.scalars.return_value.first.return_value = None
    rows.append(job_history_result)

    projects_result = MagicMock()
    projects_result.all.return_value = []
    rows.append(projects_result)

    payroll_result = MagicMock()
    payroll_result.scalar_one_or_none.return_value = None
    rows.append(payroll_result)

    db = SimpleNamespace(execute=AsyncMock(side_effect=rows))
    return db


if __name__ == "__main__":
    unittest.main()
