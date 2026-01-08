from fastapi import APIRouter, Depends
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
    return {
        "users": db.query(User).count(),
        "products": db.query(Product).count(),
        "orders": db.query(Order).count(),
        "total_revenue": float(db.query(Order.total).all()[0][0] or 0)
    }
