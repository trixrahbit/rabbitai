import logging
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

from models.models import Settings

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
DB_SECONDARY_USER = settings.DB_SECONDARY_USER
DB_SECONDARY_PASSWORD = settings.DB_SECONDARY_PASSWORD
DB_SERVER = settings.DB_SERVER
DB_NAME = settings.DB_NAME
DB_SECONDARY_NAME = settings.DB_SECONDARY_NAME

OPENID_CONFIG_URL = "https://login.botframework.com/v1/.well-known/openidconfiguration"
# Connection Strings for SQLAlchemy
PRIMARY_DATABASE_URL = (
    f"mssql+pyodbc://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_SERVER}/{settings.DB_NAME}?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
)
SECONDARY_DATABASE_URL = (
    f"mssql+pyodbc://{settings.DB_SECONDARY_USER}:{settings.DB_SECONDARY_PASSWORD}@{settings.DB_SERVER}/{settings.DB_SECONDARY_NAME}?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
)

# SQLAlchemy Engine with Connection Pooling
engine = create_engine(
    PRIMARY_DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    echo=False
)

secondary_engine = create_engine(
    SECONDARY_DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    echo=False
)

# Function to get a database connection
def get_db_connection():
    """Returns a new database connection using SQLAlchemy engine."""
    try:
        conn = engine.connect()
        logging.debug("✅ Primary database connection established successfully.")
        return conn
    except Exception as e:
        logging.error(f"❌ Primary database connection failed: {e}")
        raise

# Function to get a secondary database connection
def get_secondary_db_connection():
    """Returns a new connection to the secondary database."""
    try:
        conn = secondary_engine.connect()
        logging.debug("✅ Secondary database connection established successfully.")
        return conn
    except Exception as e:
        logging.error(f"❌ Secondary database connection failed: {e}")
        raise

# Ensure connections are closed properly
def close_db_connection(conn):
    """Closes the given database connection."""
    try:
        conn.close()
        logging.debug("🔌 Database connection closed.")
    except Exception as e:
        logging.error(f"⚠️ Error closing connection: {e}")

# Logging configuration
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
