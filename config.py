import logging
import pyodbc
from pydantic_settings import BaseSettings

# Config
class Settings(BaseSettings):
    CLIENT_ID: str
    TENANT_ID: str
    CLIENT_SECRET: str
    BOT_CLIENT_ID: str
    BOT_CLIENT_SECRET: str
    API_KEY: str  # For API key-based security
    APP_ID: str
    APP_SECRET: str
    AZURE_API_KEY: str
    AZURE_OPENAI_ENDPOINT: str
    DEPLOYMENT_NAME: str
    DB_USER: str
    DB_PASSWORD: str

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
BOT_CLIENT_ID = settings.BOT_CLIENT_ID
BOT_CLIENT_SECRET = settings.BOT_CLIENT_SECRET
DB_USER = settings.DB_USER
DB_PASSWORD = settings.DB_PASSWORD

OPENID_CONFIG_URL = "https://login.botframework.com/v1/.well-known/openidconfiguration"

def get_db_connection():
    try:
        conn = pyodbc.connect(
            f"Driver={{ODBC Driver 18 for SQL Server}};"
            f"Server=tcp:rewst.database.windows.net,1433;"
            f"Database=rabbitops;"
            f"Uid={DB_USER};"
            f"Pwd={DB_PASSWORD};"
            f"Encrypt=yes;"
            f"TrustServerCertificate=yes;"
            f"Connection Timeout=30;"
        )
        logging.debug("Database connection established successfully.")
        return conn
    except pyodbc.Error as e:
        logging.error(f"Failed to connect to the database: {e}")
        raise

# Logging configuration
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
