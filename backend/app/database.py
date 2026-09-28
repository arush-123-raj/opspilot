import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

# Load environment variables from the root .env file
load_dotenv(dotenv_path="../.env")

USER = os.getenv("POSTGRES_USER", "opspilot_user")
PASSWORD = os.getenv("POSTGRES_PASSWORD", "opspilot_password")
DB = os.getenv("POSTGRES_DB", "opspilot_db")
PORT = os.getenv("POSTGRES_PORT", "5432")

# Override 'postgres' host to 'localhost' since we are running uvicorn on the host machine
HOST = os.getenv("POSTGRES_HOST", "localhost")
if HOST == "postgres":
    HOST = "localhost"

# Construct the Asyncpg connection string
SQLALCHEMY_DATABASE_URL = f"postgresql+asyncpg://{USER}:{PASSWORD}@{HOST}:{PORT}/{DB}"

# Create the async engine
engine = create_async_engine(SQLALCHEMY_DATABASE_URL, echo=False, future=True)

# Create a configured "Session" class
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

# Base class for declarative ORM models
Base = declarative_base()

# Dependency for FastAPI endpoints to yield a database session
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
