from pydantic_settings import BaseSettings 

class Settings(BaseSettings):
    app_name: str = "Ticketing System"
    debug: bool = True 
    database_url: str = "postgresql://postgres:Camoris0605@localhost:5432/ticketing"
    secret_key: str = "change-this-secret-key-at-least-32-chars"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

settings = Settings()
