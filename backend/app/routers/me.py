from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import json

from app.database import get_db
from app.deps import get_current_user
from app.models import User, UserProfile, AccountMember, Account
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
