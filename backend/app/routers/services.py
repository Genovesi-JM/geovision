# routers/services.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import ServiceRequest

router = APIRouter(prefix="/services", tags=["Services"])

# CRIAR SERVIÇO
@router.post("/")
def request_service(
    user_id: int,
    service_type: str,
    location: str,
    hectares: float,
    db: Session = Depends(get_db)
):
    req = ServiceRequest(
        user_id=user_id,
        service_type=service_type,
        location=location,
        hectares=hectares
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req

# LISTAR
@router.get("/user/{user_id}")
def list_user_services(user_id: int, db: Session = Depends(get_db)):
    return db.query(ServiceRequest).filter(ServiceRequest.user_id == user_id).all()

# ATUALIZAR STATUS
@router.patch("/{service_id}/status")
def update_status(service_id: int, status: str, db: Session = Depends(get_db)):
    s = db.query(ServiceRequest).filter(ServiceRequest.id == service_id).first()
    if not s:
        raise ValueError("Serviço não encontrado")
    
    s.status = status
    db.commit()
    return s
