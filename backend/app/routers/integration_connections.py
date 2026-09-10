"""Customer-owner control plane for tenant-scoped external integrations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.deps import get_authorization_context, get_current_user
from app.integrations.registry import get_feature_flag_evaluator
from app.integrations.registry.validation import RedactedValidationRoute
from app.models import User
from app.modules.identity.domain import AuthorizationContext
from app.modules.integration_registry.domain import IntegrationRegistryError
from app.modules.integration_registry.schemas import (
    ConnectionLifecycleRequest,
    FeatureFlagOverrideOut,
    FeatureFlagOverridePut,
    FeatureFlagResolutionOut,
    IntegrationConnectionCreate,
    IntegrationConnectionOut,
    IntegrationConnectionUpdate,
    IntegrationHealthOut,
    IntegrationSyncEventOut,
    IntegrationSyncRetryRequest,
    IntegrationSyncRunCreate,
    IntegrationSyncRunOut,
)
from app.modules.integration_registry.services import (
    check_connection_health,
    connection_out,
    create_connection,
    delete_feature_flag_override,
    disconnect_connection,
    flag_out,
    get_connection,
    integration_entitled,
    list_connections,
    list_feature_flag_overrides,
    list_sync_events,
    list_sync_runs,
    put_feature_flag_override,
    request_sync_run,
    resolve_feature_flag,
    retry_sync_run,
    set_connection_enabled,
    sync_event_out,
    sync_run_out,
    update_connection,
)
from app.modules.organizations.domain import permission_granted


router = APIRouter(
    prefix="/integration-connections",
    tags=["integration-connections"],
    route_class=RedactedValidationRoute,
)


def _raise_domain(exc: IntegrationRegistryError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc)},
    ) from exc


def _scope(
    context: AuthorizationContext,
    *,
    required_permission: str,
) -> tuple[str, str | None]:
    organization_id = context.active_organization_id
    if not organization_id or not permission_granted(
        context.permissions, required_permission
    ):
        raise HTTPException(
            status_code=404, detail="Integration scope is not accessible"
        )
    return organization_id, context.active_workspace_id


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "integration_registry_write_conflict",
                "message": "The integration registry changed; refresh and retry",
            },
        ) from exc


@router.get("/feature-flags", response_model=list[FeatureFlagOverrideOut])
def get_feature_flags(
    workspace_id: str | None = Query(default=None, max_length=36),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
) -> list[FeatureFlagOverrideOut]:
    organization_id, active_workspace_id = _scope(
        context, required_permission="organization:read"
    )
    try:
        rows = list_feature_flag_overrides(
            db,
            organization_id=organization_id,
            active_workspace_id=active_workspace_id,
            workspace_id=workspace_id,
        )
    except IntegrationRegistryError as exc:
        _raise_domain(exc)
    return [flag_out(row) for row in rows]


@router.get(
    "/feature-flags/resolve/{flag_key:path}",
    response_model=FeatureFlagResolutionOut,
)
def get_feature_flag_resolution(
    flag_key: str,
    workspace_id: str = Query(min_length=1, max_length=36),
    member_user_id: str | None = Query(default=None, max_length=36),
    actor: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
) -> FeatureFlagResolutionOut:
    organization_id, active_workspace_id = _scope(
        context, required_permission="organization:read"
    )
    if active_workspace_id and workspace_id != active_workspace_id:
        raise HTTPException(
            status_code=404, detail="Feature flag scope is not accessible"
        )
    if (
        member_user_id
        and member_user_id != actor.id
        and not permission_granted(context.permissions, "organization:manage")
    ):
        raise HTTPException(
            status_code=404, detail="Feature flag scope is not accessible"
        )
    try:
        return resolve_feature_flag(
            db,
            flag_key=flag_key,
            organization_id=organization_id,
            workspace_id=workspace_id,
            member_user_id=member_user_id or actor.id,
            authorized=permission_granted(
                context.permissions,
                "organization:read",
            ),
            entitled=integration_entitled(
                db,
                organization_id=organization_id,
            ),
            evaluator=get_feature_flag_evaluator(),
        )
    except IntegrationRegistryError as exc:
        _raise_domain(exc)


@router.put(
    "/feature-flags/{flag_key:path}",
    response_model=FeatureFlagOverrideOut,
)
def upsert_feature_flag(
    flag_key: str,
    payload: FeatureFlagOverridePut,
    actor: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
) -> FeatureFlagOverrideOut:
    organization_id, active_workspace_id = _scope(
        context, required_permission="organization:manage"
    )
    try:
        row, _created = put_feature_flag_override(
            db,
            flag_key=flag_key,
            payload=payload,
            actor=actor,
            organization_id=organization_id,
            active_workspace_id=active_workspace_id,
        )
        _commit(db)
        db.refresh(row)
        return flag_out(row)
    except IntegrationRegistryError as exc:
        db.rollback()
        _raise_domain(exc)


@router.delete(
    "/feature-flags/overrides/{override_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_feature_flag(
    override_id: str,
    expected_version: int = Query(ge=1),
    actor: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
) -> None:
    organization_id, active_workspace_id = _scope(
        context, required_permission="organization:manage"
    )
    try:
        delete_feature_flag_override(
            db,
            override_id=override_id,
            expected_version=expected_version,
            actor=actor,
            organization_id=organization_id,
            active_workspace_id=active_workspace_id,
        )
        _commit(db)
    except IntegrationRegistryError as exc:
        db.rollback()
        _raise_domain(exc)


@router.get("", response_model=list[IntegrationConnectionOut])
def get_connections(
    provider_family: str | None = Query(default=None, max_length=80),
    include_disconnected: bool = False,
    actor: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
) -> list[IntegrationConnectionOut]:
    organization_id, workspace_id = _scope(
        context, required_permission="organization:read"
    )
    rows = list_connections(
        db,
        organization_id=organization_id,
        active_workspace_id=workspace_id,
        actor_user_id=actor.id,
        provider_family=provider_family,
        include_disconnected=include_disconnected,
    )
    return [connection_out(row) for row in rows]


@router.post(
    "",
    response_model=IntegrationConnectionOut,
    status_code=status.HTTP_201_CREATED,
)
def post_connection(
    payload: IntegrationConnectionCreate,
    actor: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
) -> IntegrationConnectionOut:
    organization_id, workspace_id = _scope(
        context, required_permission="organization:manage"
    )
    try:
        row = create_connection(
            db,
            payload=payload,
            actor=actor,
            organization_id=organization_id,
            active_workspace_id=workspace_id,
        )
        _commit(db)
        db.refresh(row)
        return connection_out(row)
    except IntegrationRegistryError as exc:
        db.rollback()
        _raise_domain(exc)


@router.get("/{connection_id}", response_model=IntegrationConnectionOut)
def get_connection_by_id(
    connection_id: str,
    actor: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
) -> IntegrationConnectionOut:
    organization_id, workspace_id = _scope(
        context, required_permission="organization:read"
    )
    try:
        return connection_out(
            get_connection(
                db,
                connection_id=connection_id,
                organization_id=organization_id,
                active_workspace_id=workspace_id,
                actor_user_id=actor.id,
            )
        )
    except IntegrationRegistryError as exc:
        _raise_domain(exc)


@router.patch("/{connection_id}", response_model=IntegrationConnectionOut)
def patch_connection(
    connection_id: str,
    payload: IntegrationConnectionUpdate,
    actor: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
) -> IntegrationConnectionOut:
    organization_id, workspace_id = _scope(
        context, required_permission="organization:manage"
    )
    try:
        row = get_connection(
            db,
            connection_id=connection_id,
            organization_id=organization_id,
            active_workspace_id=workspace_id,
            actor_user_id=actor.id,
        )
        update_connection(db, row=row, payload=payload, actor=actor)
        _commit(db)
        db.refresh(row)
        return connection_out(row)
    except IntegrationRegistryError as exc:
        db.rollback()
        _raise_domain(exc)


@router.post("/{connection_id}/enable", response_model=IntegrationConnectionOut)
def enable_connection(
    connection_id: str,
    payload: ConnectionLifecycleRequest,
    actor: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
) -> IntegrationConnectionOut:
    return _set_enabled(
        connection_id=connection_id,
        payload=payload,
        enabled=True,
        actor=actor,
        context=context,
        db=db,
    )


@router.post("/{connection_id}/disable", response_model=IntegrationConnectionOut)
def disable_connection(
    connection_id: str,
    payload: ConnectionLifecycleRequest,
    actor: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
) -> IntegrationConnectionOut:
    return _set_enabled(
        connection_id=connection_id,
        payload=payload,
        enabled=False,
        actor=actor,
        context=context,
        db=db,
    )


def _set_enabled(
    *,
    connection_id: str,
    payload: ConnectionLifecycleRequest,
    enabled: bool,
    actor: User,
    context: AuthorizationContext,
    db: Session,
) -> IntegrationConnectionOut:
    organization_id, workspace_id = _scope(
        context, required_permission="organization:manage"
    )
    try:
        row = get_connection(
            db,
            connection_id=connection_id,
            organization_id=organization_id,
            active_workspace_id=workspace_id,
            actor_user_id=actor.id,
        )
        set_connection_enabled(
            db,
            row=row,
            enabled=enabled,
            expected_version=payload.expected_version,
            actor=actor,
            reason=payload.reason,
        )
        _commit(db)
        db.refresh(row)
        return connection_out(row)
    except IntegrationRegistryError as exc:
        db.rollback()
        _raise_domain(exc)


@router.post("/{connection_id}/disconnect", response_model=IntegrationConnectionOut)
def revoke_connection(
    connection_id: str,
    payload: ConnectionLifecycleRequest,
    actor: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
) -> IntegrationConnectionOut:
    organization_id, workspace_id = _scope(
        context, required_permission="organization:manage"
    )
    try:
        row = get_connection(
            db,
            connection_id=connection_id,
            organization_id=organization_id,
            active_workspace_id=workspace_id,
            actor_user_id=actor.id,
        )
        disconnect_connection(
            db,
            row=row,
            expected_version=payload.expected_version,
            actor=actor,
            reason=payload.reason,
        )
        _commit(db)
        db.refresh(row)
        return connection_out(row)
    except IntegrationRegistryError as exc:
        db.rollback()
        _raise_domain(exc)


@router.post("/{connection_id}/health", response_model=IntegrationHealthOut)
def post_health_check(
    connection_id: str,
    actor: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
) -> IntegrationHealthOut:
    organization_id, workspace_id = _scope(
        context, required_permission="organization:manage"
    )
    try:
        row = get_connection(
            db,
            connection_id=connection_id,
            organization_id=organization_id,
            active_workspace_id=workspace_id,
            actor_user_id=actor.id,
        )
        result = check_connection_health(db, row=row, actor=actor)
        _commit(db)
        return result
    except IntegrationRegistryError as exc:
        db.rollback()
        _raise_domain(exc)


@router.get(
    "/{connection_id}/sync-runs",
    response_model=list[IntegrationSyncRunOut],
)
def get_sync_runs(
    connection_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    actor: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
) -> list[IntegrationSyncRunOut]:
    organization_id, workspace_id = _scope(
        context, required_permission="organization:read"
    )
    try:
        connection = get_connection(
            db,
            connection_id=connection_id,
            organization_id=organization_id,
            active_workspace_id=workspace_id,
            actor_user_id=actor.id,
        )
        return [
            sync_run_out(row)
            for row in list_sync_runs(
                db,
                connection=connection,
                active_workspace_id=workspace_id,
                limit=limit,
            )
        ]
    except IntegrationRegistryError as exc:
        _raise_domain(exc)


@router.post(
    "/{connection_id}/sync-runs",
    response_model=IntegrationSyncRunOut,
    status_code=status.HTTP_201_CREATED,
)
def post_sync_run(
    connection_id: str,
    payload: IntegrationSyncRunCreate,
    actor: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
) -> IntegrationSyncRunOut:
    organization_id, workspace_id = _scope(
        context, required_permission="organization:manage"
    )
    try:
        connection = get_connection(
            db,
            connection_id=connection_id,
            organization_id=organization_id,
            active_workspace_id=workspace_id,
            actor_user_id=actor.id,
        )
        row, _created = request_sync_run(
            db,
            connection=connection,
            payload=payload,
            actor=actor,
            active_workspace_id=workspace_id,
            feature_flag_evaluator=get_feature_flag_evaluator(),
        )
        _commit(db)
        db.refresh(row)
        return sync_run_out(row)
    except IntegrationRegistryError as exc:
        db.rollback()
        _raise_domain(exc)


@router.post(
    "/{connection_id}/sync-runs/{run_id}/retry",
    response_model=IntegrationSyncRunOut,
)
def post_sync_retry(
    connection_id: str,
    run_id: str,
    payload: IntegrationSyncRetryRequest,
    actor: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
) -> IntegrationSyncRunOut:
    organization_id, workspace_id = _scope(
        context, required_permission="organization:manage"
    )
    try:
        connection = get_connection(
            db,
            connection_id=connection_id,
            organization_id=organization_id,
            active_workspace_id=workspace_id,
            actor_user_id=actor.id,
        )
        row = retry_sync_run(
            db,
            connection=connection,
            run_id=run_id,
            payload=payload,
            actor=actor,
            active_workspace_id=workspace_id,
            feature_flag_evaluator=get_feature_flag_evaluator(),
        )
        _commit(db)
        db.refresh(row)
        return sync_run_out(row)
    except IntegrationRegistryError as exc:
        db.rollback()
        _raise_domain(exc)


@router.get(
    "/{connection_id}/sync-events",
    response_model=list[IntegrationSyncEventOut],
)
def get_sync_events(
    connection_id: str,
    run_id: str | None = Query(default=None, max_length=36),
    limit: int = Query(default=200, ge=1, le=500),
    actor: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
) -> list[IntegrationSyncEventOut]:
    organization_id, workspace_id = _scope(
        context, required_permission="organization:read"
    )
    try:
        connection = get_connection(
            db,
            connection_id=connection_id,
            organization_id=organization_id,
            active_workspace_id=workspace_id,
            actor_user_id=actor.id,
        )
        return [
            sync_event_out(row)
            for row in list_sync_events(
                db,
                connection=connection,
                active_workspace_id=workspace_id,
                run_id=run_id,
                limit=limit,
            )
        ]
    except IntegrationRegistryError as exc:
        _raise_domain(exc)


__all__ = ["router"]
