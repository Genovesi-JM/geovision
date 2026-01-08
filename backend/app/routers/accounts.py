import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_current_account
from ..database import get_db
from ..models import Account, AccountMember, User
from ..schemas import AccountCreate, AccountPublic, AccountSwitchRequest

router = APIRouter(prefix="/accounts", tags=["accounts"])

DEFAULT_MODULES: List[str] = ["kpi", "projects", "store", "alerts"]


def _parse_modules(value: str) -> List[str]:
    try:
        parsed = json.loads(value) if value else None
        return parsed if isinstance(parsed, list) else DEFAULT_MODULES
    except Exception:
        return DEFAULT_MODULES


@router.get("", response_model=List[AccountPublic])
def list_accounts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    memberships = db.query(AccountMember).filter(AccountMember.user_id == user.id).all()
    account_ids = [m.account_id for m in memberships]
    if not account_ids:
        return []

    accounts = db.query(Account).filter(Account.id.in_(account_ids)).order_by(Account.created_at.desc()).all()
    results: List[AccountPublic] = []
    for acct in accounts:
        member = next((m for m in memberships if m.account_id == acct.id), None)
        results.append(
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
    return results


@router.post("", response_model=AccountPublic, status_code=status.HTTP_201_CREATED)
def create_account(payload: AccountCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    modules = payload.modules_enabled or DEFAULT_MODULES

    account = Account(
        name=payload.name,
        sector_focus=payload.sector_focus,
        entity_type=payload.entity_type,
        org_name=payload.org_name,
        modules_enabled=json.dumps(modules),
    )
    db.add(account)
    db.flush()

    membership = AccountMember(account_id=account.id, user_id=user.id, role="owner")
    db.add(membership)

    db.commit()
    db.refresh(account)

    return AccountPublic(
        id=account.id,
        name=account.name,
        sector_focus=account.sector_focus,
        entity_type=account.entity_type,
        org_name=account.org_name,
        modules_enabled=modules,
        role="owner",
    )


@router.post("/switch")
def switch_account(payload: AccountSwitchRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    membership = (
        db.query(AccountMember)
        .filter(AccountMember.account_id == payload.account_id, AccountMember.user_id == user.id)
        .first()
    )
    if not membership:
        raise HTTPException(status_code=403, detail="Sem acesso a esta conta.")
    account = db.get(Account, payload.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Conta nAœo encontrada.")
    return {
        "account": AccountPublic(
            id=account.id,
            name=account.name,
            sector_focus=account.sector_focus,
            entity_type=account.entity_type,
            org_name=account.org_name,
            modules_enabled=_parse_modules(account.modules_enabled),
            role=membership.role,
        )
    }
