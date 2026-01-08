"""Dedicated database connection for accounts (customers/employees)."""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from ..config import settings

accounts_engine = create_engine(
    settings.accounts_database_url,
    pool_pre_ping=True,
    echo=False,
)

AccountsSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=accounts_engine,
)

AccountsBase = declarative_base()


def get_accounts_db():
    db = AccountsSessionLocal()
    try:
        yield db
    finally:
        db.close()
