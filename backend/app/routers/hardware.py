# routers/hardware.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import HardwareInstallation

router = APIRouter(prefix="/hardware", tags=["Hardware"])

@router.post("/")
def register_hardware(
    user_id: int,
    hardware_name: str,
    location: str,
    db: Session = Depends(get_db)
):
    hw = HardwareInstallation(
        user_id=user_id,
        hardware_name=hardware_name,
        location=location
    )
    db.add(hw)
    db.commit()
    db.refresh(hw)
    return hw


@router.get("/user/{user_id}")
def user_hardware(user_id: int, db: Session = Depends(get_db)):
    return db.query(HardwareInstallation).filter(HardwareInstallation.user_id == user_id).all()
