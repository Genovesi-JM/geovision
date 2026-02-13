"""Routers for employees stored in the accounts database."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.orm import Session

from ..accounts import models as account_models
from ..accounts.database import get_accounts_db

router = APIRouter()


class EmployeeBase(BaseModel):
    name: str = Field(..., max_length=200)
    email: EmailStr
    role: str = Field(..., max_length=120)
    department: Optional[str] = Field(None, max_length=120)
    phone: Optional[str] = Field(None, max_length=60)
    is_active: bool = True


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeOut(EmployeeBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


@router.get("/", response_model=List[EmployeeOut])
def list_employees(db: Session = Depends(get_accounts_db)) -> List[account_models.Employee]:
    return (
        db.query(account_models.Employee)
        .order_by(account_models.Employee.created_at.desc())
        .all()
    )


@router.post("/", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
def create_employee(
    payload: EmployeeCreate, db: Session = Depends(get_accounts_db)
) -> account_models.Employee:
    existing = (
        db.query(account_models.Employee)
        .filter(account_models.Employee.email == payload.email)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email de colaborador já registado."
        )

    employee = account_models.Employee(**payload.dict())
    db.add(employee)
    db.commit()
    db.refresh(employee)
    return employee
