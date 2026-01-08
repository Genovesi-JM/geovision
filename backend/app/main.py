# backend/app/main.py

from pathlib import Path

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

    # CORS – em dev deixamos aberto, em produção restringes ao dominio do frontend
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
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
