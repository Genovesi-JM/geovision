"""ERP integration status and controlled outbox processing."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.integration import IntegrationError
from app.deps import get_current_user
from app.integrations.erp import get_erp_adapter
from app.models import IntegrationOutbox, User
from app.modules.organizations.services import get_user_company_id

_get_user_company_id = get_user_company_id
from app.services.erp_sync import process_pending

router = APIRouter(prefix="/integrations/erp", tags=["integrations"])


@router.get("/status")
def status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        provider = get_erp_adapter().health()
    except IntegrationError as exc:
        provider = {
            "provider": exc.provider,
            "configured": False,
            "mode": "blocked",
            "code": exc.code,
            "reason": exc.safe_message,
        }
    company_id = _get_user_company_id(user, db)
    queue = db.query(IntegrationOutbox).filter(IntegrationOutbox.company_id == company_id)
    return {
        **provider,
        "pending": queue.filter(IntegrationOutbox.status == "pending").count(),
        "failed": queue.filter(
            IntegrationOutbox.status.in_(["failed", "failed_terminal"])
        ).count(),
    }


@router.post("/sync")
def sync(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role not in {"admin", "superadmin"}:
        raise HTTPException(status_code=403, detail="Administrator access required")
    try:
        return process_pending(db)
    except IntegrationError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"ERP provider is unavailable: {exc.safe_message}",
        ) from exc
