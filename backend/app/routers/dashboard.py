from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session
from ..database import SessionLocal
from ..models import User, Product, Order

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    total_revenue = db.query(func.coalesce(func.sum(Order.total), 0)).scalar()
    return {
        "users": db.query(User).count(),
        "products": db.query(Product).count(),
        "orders": db.query(Order).count(),
        "total_revenue": float(total_revenue)
    }
