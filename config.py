from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    CLIENT_ID: str
    TENANT_ID: str
    CLIENT_SECRET: str
    API_KEY: str  # For API key-based security

    class Config:
        env_file = ".env"

settings = Settings()


# Azure OpenAI settings for generating recommendations
AZURE_OPENAI_ENDPOINT = "https://webit.openai.azure.com/"
AZURE_OPENAI_DEPLOYMENT = "rabbit_smart"
AZURE_API_KEY = "91b76cbcc9da4055bd966a0809476c04"