"""ERP integration status and controlled outbox processing."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.integrations.erp import get_erp_adapter
from app.models import IntegrationOutbox, User
from app.routers.me import _get_user_company_id
from app.services.erp_sync import process_pending

router = APIRouter(prefix="/integrations/erp", tags=["integrations"])


@router.get("/status")
def status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        provider = get_erp_adapter().health()
    except RuntimeError as exc:
        provider = {"provider": "erpnext", "configured": False, "mode": "blocked", "reason": str(exc)}
    company_id = _get_user_company_id(user, db)
    queue = db.query(IntegrationOutbox).filter(IntegrationOutbox.company_id == company_id)
    return {
        **provider,
        "pending": queue.filter(IntegrationOutbox.status == "pending").count(),
        "failed": queue.filter(IntegrationOutbox.status == "failed").count(),
    }


@router.post("/sync")
def sync(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role not in {"admin", "superadmin"}:
        raise HTTPException(status_code=403, detail="Administrator access required")
    return process_pending(db)
