from pydantic import BaseSettings

class Settings(BaseSettings):
    CLIENT_ID: str
    TENANT_ID: str
    CLIENT_SECRET: str
    API_KEY: str  # For API key-based security

    class Config:
        env_file = ".env"

settings = Settings()
