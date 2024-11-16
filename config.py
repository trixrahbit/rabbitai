import os

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

APP_ID = os.getenv("APP_ID")
APP_SECRET = os.getenv("APP_SECRET")
AZURE_API_KEY = os.getenv("AZURE_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
deployment_name = os.getenv("DEPLOYMENT_NAME")



logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)