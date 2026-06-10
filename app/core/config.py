from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "LimaStock"
    APP_ENV: str = "local"
    APP_DEBUG: bool = True

    API_PREFIX: str = "/api/v1"

    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_JWT_AUDIENCE: str = "authenticated"

    FRONTEND_URL: str = "http://localhost:3000"

    ASAAS_BASE_URL: str = "https://api-sandbox.asaas.com/v3"
    ASAAS_API_KEY: str
    ASAAS_WEBHOOK_TOKEN: str

    PLATFORM_ADMIN_EMAILS: str = "d175259@dac.unicamp.br"

    COOKIE_ACCESS_NAME: str = "limastock_access_token"
    COOKIE_REFRESH_NAME: str = "limastock_refresh_token"
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()


def get_platform_admin_emails() -> set[str]:
    return {
        email.strip().lower()
        for email in settings.PLATFORM_ADMIN_EMAILS.split(",")
        if email.strip()
    }