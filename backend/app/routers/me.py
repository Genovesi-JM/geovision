from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pathlib import Path
from typing import List, Optional
import json

from app.database import get_db
from app.deps import get_current_user
from app.models import User, UserProfile, AccountMember, Account, CompanyUser, Company
from app.schemas import AccountPublic, MeResponse, ProfileOut, UserSummary

router = APIRouter(prefix="/me", tags=["me"])


def _parse_modules(value: str):
    try:
        parsed = json.loads(value) if value else None
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


@router.get("", response_model=MeResponse)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    prof = db.get(UserProfile, user.id)

    memberships = db.query(AccountMember).filter(AccountMember.user_id == user.id).all()
    account_ids = [m.account_id for m in memberships]

    accounts = []
    default_account_id = None
    if account_ids:
        rows = db.query(Account).filter(Account.id.in_(account_ids)).order_by(Account.created_at.desc()).all()
        for acct in rows:
            member = next((m for m in memberships if m.account_id == acct.id), None)
            accounts.append(
                AccountPublic(
                    id=acct.id,
                    name=acct.name,
                    sector_focus=acct.sector_focus,
                    entity_type=acct.entity_type,
                    org_name=acct.org_name,
                    modules_enabled=_parse_modules(acct.modules_enabled),
                    role=member.role if member else None,
                )
            )
        owner = next((m for m in memberships if m.role == "owner"), memberships[0])
        default_account_id = owner.account_id if owner else None

    return MeResponse(
        user=UserSummary(id=user.id, email=user.email, role=user.role, full_name=prof.full_name if prof else None),
        profile=ProfileOut.model_validate(prof) if prof else None,
        accounts=accounts,
        default_account_id=default_account_id,
    )


# ============ CLIENT DOCUMENTS ============

def _get_user_company_id(user: User, db: Session) -> Optional[str]:
    """Find the company this user belongs to via company_users table, with Company fallback."""
    email = (user.email or "").strip().lower()
    cu = db.query(CompanyUser).filter(CompanyUser.email == email).first()
    if cu:
        return cu.company_id
    # Fallback: check Company table directly (for users registered before CompanyUser was added)
    company = db.query(Company).filter(Company.email == email).first()
    if company:
        # Auto-create the missing CompanyUser link
        db.add(CompanyUser(
            company_id=company.id,
            email=email,
            name=getattr(user, "full_name", None) or email,
            role="owner",
            is_active=True,
        ))
        db.commit()
        return company.id
    return None


@router.get("/documents")
def my_documents(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """List documents for the current user's company."""
    from app.models import Document as DocModel
    from sqlalchemy import or_
    company_id = _get_user_company_id(user, db)
    print(f"[me/documents] user={user.email} company_id={company_id}")
    if not company_id:
        return []
    docs = db.query(DocModel).filter(
        DocModel.company_id == company_id,
        or_(DocModel.is_confidential == False, DocModel.is_confidential.is_(None)),
    ).order_by(DocModel.created_at.desc()).all()
    print(f"[me/documents] found {len(docs)} docs for company {company_id}")
    return [{
        "id": d.id,
        "name": d.name,
        "document_type": d.document_type,
        "description": d.description,
        "status": d.status or "draft",
        "is_official": d.is_official or False,
        "file_size_bytes": d.file_size_bytes or 0,
        "mime_type": d.mime_type,
        "has_file": bool(d.file_path),
        "created_at": d.created_at.isoformat() if d.created_at else None,
    } for d in docs]


@router.get("/documents/{document_id}/download")
def download_my_document(document_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Download a document file — only if it belongs to the user's company."""
    from app.models import Document as DocModel
    company_id = _get_user_company_id(user, db)
    if not company_id:
        raise HTTPException(status_code=403, detail="No company linked")
    doc = db.get(DocModel, document_id)
    if not doc or doc.company_id != company_id:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.is_confidential:
        raise HTTPException(status_code=403, detail="Confidential document")
    if not doc.file_path:
        raise HTTPException(status_code=404, detail="No file available")
    fp = Path(doc.file_path)
    if not fp.exists():
        raise HTTPException(status_code=404, detail="File not found on server")
    return FileResponse(
        path=str(fp),
        filename=doc.name,
        media_type=doc.mime_type or "application/octet-stream",
    )
