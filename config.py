import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

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
    f"mssql+aioodbc://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_SERVER}/{settings.DB_NAME}"
    "?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
)
SECONDARY_DATABASE_URL = (
    f"mssql+aioodbc://{settings.DB_SECONDARY_USER}:{settings.DB_SECONDARY_PASSWORD}@{settings.DB_SERVER}/{settings.DB_SECONDARY_NAME}"
    "?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
)

# Create Async Engines
async_engine = create_async_engine(
    PRIMARY_DATABASE_URL,
    echo=False
)
secondary_async_engine = create_async_engine(
    SECONDARY_DATABASE_URL,
    echo=False
)

# Create async session makers
AsyncSessionLocal = sessionmaker(
    async_engine, expire_on_commit=False, class_=AsyncSession
)
SecondaryAsyncSessionLocal = sessionmaker(
    secondary_async_engine, expire_on_commit=False, class_=AsyncSession
)

# Function to get an async session for the primary database
async def get_db_connection() -> AsyncSession:
    """Returns an async database session for the primary database."""
    async with AsyncSessionLocal() as session:
        yield session  # Allows proper cleanup after use

# Function to get an async session for the secondary database
async def get_secondary_db_connection():
    """Provides an async database session."""
    async with SecondaryAsyncSessionLocal() as session:
        yield session  # ✅ This ensures correct session handling


# Logging configuration
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

