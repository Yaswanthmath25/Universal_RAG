import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv


# Load environment variables from .env (for local development)
load_dotenv()


# Read the database URL from the environment.
# On Render, this is set in the Environment tab.
# Locally, this comes from the .env file.
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is missing from environment variables")

# Render provides URLs starting with postgres:// or postgresql://
# SQLAlchemy 2.x defaults to the psycopg (v3) driver for those,
# but this project uses psycopg2. Force the driver explicitly.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://",
        "postgresql+psycopg2://",
        1
    )
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql://",
        "postgresql+psycopg2://",
        1
    )


# Create database engine
engine = create_engine(DATABASE_URL, echo=True)


# Create database sessions
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


# Base class for database models
Base = declarative_base()