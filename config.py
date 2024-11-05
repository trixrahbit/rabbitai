from pydantic_settings import BaseSettings
from openai import AzureOpenAI

class Settings(BaseSettings):
    CLIENT_ID: str
    TENANT_ID: str
    CLIENT_SECRET: str
    API_KEY: str  # For API key-based security

    class Config:
        env_file = ".env"

settings = Settings()


client = AzureOpenAI(
    azure_endpoint="https://webit.openai.azure.com",
    api_key="91b76cbcc9da4055bd966a0809476c04",
    api_version="2024-05-01-preview"
)