from pydantic_settings import BaseSettings

# Config
class Settings(BaseSettings):
    CLIENT_ID: str
    TENANT_ID: str
    CLIENT_SECRET: str
    API_KEY: str  # For API key-based security
    APP_ID: str
    APP_SECRET: str
    AZURE_API_KEY: str
    AZURE_OPENAI_ENDPOINT: str
    DEPLOYMENT_NAME: str

    class Config:
        env_file = ".env"

# Instantiate settings
settings = Settings()

# Access environment variables
APP_ID = settings.APP_ID
APP_SECRET = settings.APP_SECRET
AZURE_API_KEY = settings.AZURE_API_KEY
AZURE_OPENAI_ENDPOINT = settings.AZURE_OPENAI_ENDPOINT
deployment_name = settings.DEPLOYMENT_NAME




logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)