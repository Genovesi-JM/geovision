"""Models stored in the accounts database."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from .database import AccountsBase


class CustomerAccount(AccountsBase):
    __tablename__ = "customer_accounts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    email = Column(String(256), unique=True, nullable=False, index=True)
    company = Column(String(200), nullable=True)
    country = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Employee(AccountsBase):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    email = Column(String(256), unique=True, nullable=False, index=True)
    role = Column(String(120), nullable=False)
    department = Column(String(120), nullable=True)
    phone = Column(String(60), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
