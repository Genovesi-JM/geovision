# backend/app/main.py

from pathlib import Path

import os
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import init_db_engine
from .routers import auth, projects, ai, accounts, me, kpi
from .routers import products, orders, customer_accounts, employees
from .seed_data import (
    seed_demo_products,
    seed_demo_users,
    seed_demo_customer_accounts,
    seed_demo_employees,
)


def create_application() -> FastAPI:
    """Build and configure the FastAPI instance."""
    application = FastAPI(title=settings.app_name)

    # Safe startup diagnostics (no secrets)
    try:
        print(
            "[GeoVision] Config: "
            f"env={settings.env} "
            f"backend_base={settings.backend_base} "
            f"frontend_base={settings.frontend_base} "
            f"google_client_id_set={bool(settings.google_client_id)} "
            f"google_client_secret_set={bool(settings.google_client_secret)}"
        )
        cors_env = os.getenv("CORS_ORIGINS", "")
        if cors_env.strip():
            print(f"[GeoVision] CORS_ORIGINS(env)={cors_env}")
    except Exception:
        pass

    # CORS
    # Note: browsers will reject `Access-Control-Allow-Origin: *` when
    # `allow_credentials=True`, so we must send an explicit origin list.
    default_origins = {
        "http://127.0.0.1:8001",
        "http://localhost:8001",
        "https://genovesi-jm.github.io",
    }
    try:
        parsed = urlparse(settings.frontend_base)
        if parsed.scheme and parsed.netloc:
            default_origins.add(f"{parsed.scheme}://{parsed.netloc}")
    except Exception:
        pass

    env_origins = os.getenv("CORS_ORIGINS", "")
    if env_origins.strip():
        allow_origins = [o.strip() for o in env_origins.split(",") if o.strip()]
    else:
        allow_origins = sorted(default_origins)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    init_db_engine()

    try:
        inserted_products = seed_demo_products()
        inserted_users = seed_demo_users()
        inserted_customers = seed_demo_customer_accounts()
        inserted_employees = seed_demo_employees()
        if inserted_products:
            print(f"[GeoVision] Produtos demo inseridos: {inserted_products}")
        if inserted_users:
            print(f"[GeoVision] Utilizadores demo criados: {inserted_users}")
        if inserted_customers:
            print(f"[GeoVision] Contas de clientes demo criadas: {inserted_customers}")
        if inserted_employees:
            print(f"[GeoVision] Funcionários demo criados: {inserted_employees}")
    except Exception as exc:
        # Não travar a app se a seed falhar, apenas registar.
        print(f"[GeoVision] Falha ao semear dados demo: {exc}")

    # Routers principais existentes
    # The `auth` router already sets its own prefix (prefix="/auth"), so
    # include it without adding another prefix to avoid routes like
    # "/auth/auth/login".
    application.include_router(auth.router)
    application.include_router(projects.router, prefix="/projects", tags=["projects"])
    application.include_router(ai.router, prefix="/ai", tags=["ai"])
    application.include_router(accounts.router)
    application.include_router(me.router)
    application.include_router(kpi.router)

    # Novos routers da loja
    application.include_router(products.router, prefix="/products", tags=["products"])
    application.include_router(orders.router, prefix="/orders", tags=["orders"])
    application.include_router(
        customer_accounts.router, prefix="/accounts/customers", tags=["accounts"]
    )
    application.include_router(
        employees.router, prefix="/accounts/employees", tags=["accounts"]
    )

    @application.get("/health", tags=["system"])
    def healthcheck() -> dict:
        return {"status": "ok"}

    return application


app = create_application()
