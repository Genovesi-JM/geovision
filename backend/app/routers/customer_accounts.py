"""Routers for customer accounts stored in the accounts database."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.orm import Session

from ..accounts import models as account_models
from ..accounts.database import get_accounts_db

router = APIRouter()


class CustomerBase(BaseModel):
    name: str = Field(..., max_length=200)
    email: EmailStr
    company: Optional[str] = Field(None, max_length=200)
    country: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None


class CustomerCreate(CustomerBase):
    pass


class CustomerOut(CustomerBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


@router.get("/", response_model=List[CustomerOut])
def list_customer_accounts(db: Session = Depends(get_accounts_db)) -> List[account_models.CustomerAccount]:
    return (
        db.query(account_models.CustomerAccount)
        .order_by(account_models.CustomerAccount.created_at.desc())
        .all()
    )


@router.post("/", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
def create_customer_account(
    payload: CustomerCreate, db: Session = Depends(get_accounts_db)
) -> account_models.CustomerAccount:
    existing = (
        db.query(account_models.CustomerAccount)
        .filter(account_models.CustomerAccount.email == payload.email)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email já registado."
        )

    customer = account_models.CustomerAccount(**payload.dict())
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer
