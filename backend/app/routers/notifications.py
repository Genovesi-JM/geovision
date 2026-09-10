"""Authenticated contextual notification inbox and delivery preferences."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.deps import get_authorization_context, get_current_user
from app.models import User
from app.modules.identity.domain import AuthorizationContext
from app.modules.notifications.domain import NotificationCategory, NotificationError
from app.modules.notifications.inbox import (
    endpoint_payload,
    get_scoped_notification,
    get_visible_notification,
    list_preferences,
    mark_all_notifications_read,
    mark_notification_read,
    notification_payload,
    preference_payload,
    register_endpoint,
    revoke_endpoint,
    upsert_preference,
    visible_notifications,
)
from app.modules.notifications.schemas import (
    NotificationEndpointDeleteOut,
    NotificationEndpointOut,
    NotificationEndpointUpsert,
    NotificationListOut,
    NotificationOut,
    NotificationPreferenceOut,
    NotificationPreferencesOut,
    NotificationPreferenceUpdate,
    NotificationTargetOut,
    UnreadCountOut,
)
from app.modules.notifications.security import resolve_notification_target


router = APIRouter(tags=["notifications"])


def _http_error(exc: NotificationError) -> HTTPException:
    code = {
        "notification_not_found": status.HTTP_404_NOT_FOUND,
        "target_not_found": status.HTTP_404_NOT_FOUND,
        "target_unavailable": status.HTTP_404_NOT_FOUND,
        "organization_not_found": status.HTTP_404_NOT_FOUND,
        "endpoint_not_found": status.HTTP_404_NOT_FOUND,
        "version_conflict": status.HTTP_409_CONFLICT,
        "invalid_installation": status.HTTP_400_BAD_REQUEST,
        "endpoint_protection_failed": status.HTTP_503_SERVICE_UNAVAILABLE,
        "unsupported_endpoint_provider": status.HTTP_400_BAD_REQUEST,
    }.get(exc.code, status.HTTP_400_BAD_REQUEST)
    return HTTPException(
        status_code=code,
        detail={"code": exc.code, "message": str(exc)},
    )


@router.get("/notifications", response_model=NotificationListOut)
def read_notifications(
    organization_id: str | None = Query(default=None, max_length=36),
    workspace_id: str | None = Query(default=None, max_length=36),
    category: NotificationCategory | None = None,
    unread_only: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    rows, total, unread = visible_notifications(
        db,
        context=context,
        organization_id=organization_id,
        workspace_id=workspace_id,
        category=category.value if category else None,
        unread_only=unread_only,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [notification_payload(row) for row in rows],
        "total": total,
        "unread": unread,
    }


@router.get("/notifications/unread-count", response_model=UnreadCountOut)
def unread_notification_count(
    organization_id: str | None = Query(default=None, max_length=36),
    workspace_id: str | None = Query(default=None, max_length=36),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    _, _, unread = visible_notifications(
        db,
        context=context,
        organization_id=organization_id,
        workspace_id=workspace_id,
        limit=1,
    )
    return {"unread": unread}


@router.post("/notifications/{notification_id}/read", response_model=NotificationOut)
def read_one_notification(
    notification_id: str,
    actor: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    try:
        row = mark_notification_read(
            db,
            context=context,
            actor=actor,
            notification_id=notification_id,
        )
        db.commit()
        db.refresh(row)
        return notification_payload(row)
    except NotificationError as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.post("/notifications/read-all", response_model=UnreadCountOut)
def read_all_notifications(
    organization_id: str | None = Query(default=None, max_length=36),
    actor: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    mark_all_notifications_read(
        db,
        context=context,
        actor=actor,
        organization_id=organization_id,
    )
    db.commit()
    return {"unread": 0}


@router.get("/notifications/{notification_id}/target", response_model=NotificationTargetOut)
def read_notification_target(
    notification_id: str,
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    try:
        notification = get_scoped_notification(
            db,
            context=context,
            notification_id=notification_id,
        )
        target = resolve_notification_target(
            db,
            context=context,
            notification=notification,
        )
        return {
            "notification_id": notification.id,
            "target_type": target.target_type,
            "target_id": target.target_id,
            "workspace_id": target.workspace_id,
            "app_path": target.app_path,
            "portal_path": target.portal_path,
        }
    except NotificationError as exc:
        raise _http_error(exc) from exc


@router.get("/notification-preferences", response_model=NotificationPreferencesOut)
def read_notification_preferences(
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    return {"items": [preference_payload(row) for row in list_preferences(db, context=context)]}


@router.put("/notification-preferences", response_model=NotificationPreferenceOut)
def write_notification_preference(
    payload: NotificationPreferenceUpdate,
    actor: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    try:
        row = upsert_preference(
            db,
            context=context,
            actor=actor,
            data=payload,
        )
        db.commit()
        db.refresh(row)
        return preference_payload(row)
    except NotificationError as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.put(
    "/notification-endpoints/{installation_id}",
    response_model=NotificationEndpointOut,
)
def write_notification_endpoint(
    installation_id: str,
    payload: NotificationEndpointUpsert,
    actor: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    try:
        row = register_endpoint(
            db,
            context=context,
            actor=actor,
            installation_id=installation_id,
            data=payload,
        )
        db.commit()
        db.refresh(row)
        return endpoint_payload(row)
    except NotificationError as exc:
        db.rollback()
        raise _http_error(exc) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "endpoint_conflict",
                "message": "This notification endpoint is already registered",
            },
        ) from exc


@router.delete(
    "/notification-endpoints/{installation_id}",
    response_model=NotificationEndpointDeleteOut,
)
def delete_notification_endpoint(
    installation_id: str,
    actor: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    revoked = revoke_endpoint(
        db,
        context=context,
        actor=actor,
        installation_id=installation_id,
    )
    db.commit()
    return {"installation_id": installation_id, "revoked": revoked}


__all__ = ["router"]
