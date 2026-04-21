from pydantic_settings import BaseSettings 

class Settings(BaseSettings):
    app_name: str = "Ticketing System"
    debug: bool = True 
    database_url: str = "postgresql://postgres:Camoris0605@localhost:5432/ticketing"

settings = Settings()