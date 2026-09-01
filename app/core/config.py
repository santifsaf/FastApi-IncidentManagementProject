from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="APP_")

    app_name: str = "Ticketing System"
    debug: bool = True 
    database_url: str
    # Base aislada para tests de integracion. Si no se configura, los tests
    # derivan una URL terminada en "_test" sin tocar la base de desarrollo.
    test_database_url: str | None = None
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    archive_closed_tickets_after_days: int = 30

settings = Settings()
