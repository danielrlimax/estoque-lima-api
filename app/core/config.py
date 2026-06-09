from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Estoque SaaS"
    APP_ENV: str = "local"
    APP_DEBUG: bool = True

    API_PREFIX: str = "/api/v1"

    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str | None = None
    SUPABASE_JWT_AUDIENCE: str = "authenticated"

    FRONTEND_URL: str = "http://localhost:3000"

    ASAAS_BASE_URL: str = "https://api-sandbox.asaas.com/v3"
    ASAAS_API_KEY: str = "sua_chave_sandbox_asaas"
    ASAAS_WEBHOOK_TOKEN: str = "troque_esse_token"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()