from pydantic_settings import BaseSettings
from openai import AzureOpenAI
import logging

class Settings(BaseSettings):
    CLIENT_ID: str
    TENANT_ID: str
    CLIENT_SECRET: str
    API_KEY: str  # For API key-based security

    class Config:
        env_file = ".env"

settings = Settings()



AZURE_OPENAI_ENDPOINT = "https://webit.openai.azure.com"
AZURE_API_KEY = "91b76cbcc9da4055bd966a0809476c04"
deployment_name = "rabbit_smart"



logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)