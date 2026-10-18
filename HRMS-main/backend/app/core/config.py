import secrets

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Mock HRMS API"
    environment: str = "dev"
    app_timezone: str = "Asia/Kolkata"
    database_url: str = "sqlite+aiosqlite:///./storage/hrms.db"

    jwt_secret_key: str = ""
    seed_password: str | None = None
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    policy_upload_dir: str = "/app/storage/hr-policies"
    profile_photo_upload_dir: str = "/app/storage/profile-photos"
    employee_document_upload_dir: str = "/app/storage/employee-documents"
    groq_api_key: str | None = None
    llm_model: str = "openai/gpt-oss-120b"
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_timeout_seconds: float = 30.0

    @model_validator(mode="after")
    def require_production_jwt_secret(self):
        environment = self.environment.casefold()
        if environment in {"dev", "development", "test"}:
            if self.jwt_secret_key == "change_me" or len(self.jwt_secret_key) < 32:
                # Never run local development with a source-controlled, guessable JWT key.
                self.jwt_secret_key = secrets.token_urlsafe(48)
        elif self.jwt_secret_key == "change_me" or len(self.jwt_secret_key) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters outside development and test")
        return self


settings = Settings()
