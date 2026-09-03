from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuracion central cargada desde variables APP_* y el archivo .env."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="APP_")

    app_name: str = "Ticketing System"
    debug: bool = True 
    database_url: str
    # Nunca debe apuntar a la base de desarrollo. Si queda vacia, la
    # infraestructura de tests deriva un nombre terminado en "_test".
    test_database_url: str | None = None
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    archive_closed_tickets_after_days: int = 30

settings = Settings()
