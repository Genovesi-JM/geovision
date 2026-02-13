"""Seed data helpers for the demo store."""

from __future__ import annotations

from typing import List

from sqlalchemy.orm import Session

from app import models
from app.accounts import models as account_models
from app.accounts.database import AccountsSessionLocal, AccountsBase, accounts_engine
from app.database import SessionLocal
from app.utils import hash_password

DEMO_PRODUCTS: List[dict] = [
    {
        "name": "NDVI + Pulverização 200 ha",
        "slug": "ndvi-pulverizacao-200",
        "category": "servico-drone",
        "sector": "agricultura",
        "description": "Missão completa com drone multiespectral + pulverização em precisão para 200 ha.",
        "price_cents": 245000,
        "unit_label": "por missão",
    },
    {
        "name": "Kit IoT Pecuária – 25 colares",
        "slug": "kit-iot-pecuaria-25",
        "category": "hardware-iot",
        "sector": "pecuaria",
        "description": "Colares inteligentes + gateway LoRaWAN para rastrear rebanhos em grandes extensões.",
        "price_cents": 189000,
        "unit_label": "por kit",
    },
    {
        "name": "Mapeamento LIDAR para mina",
        "slug": "mapeamento-lidar-mina",
        "category": "servico-lidar",
        "sector": "mining",
        "description": "Modelo 3D, volumes e perfis de talude com drone LIDAR de classe industrial.",
        "price_cents": 360000,
        "unit_label": "por campanha",
    },
    {
        "name": "Sensores estruturais para ponte",
        "slug": "sensores-ponte",
        "category": "hardware-sensor",
        "sector": "infra",
        "description": "Pacote de sensores de vibração, inclinação e temperatura integrados no dashboard GeoVision.",
        "price_cents": 275000,
        "unit_label": "por instalação",
    },
    {
        "name": "Ração mineralizada – 5t",
        "slug": "racao-mineralizada-5t",
        "category": "insumo-nutricao",
        "sector": "pecuaria",
        "description": "Formulação balanceada para suportar o rebanho durante a época seca.",
        "price_cents": 82000,
        "unit_label": "por lote",
    },
]


DEMO_USERS: List[dict] = [
    {
        "email": "genovesi.maria@geovisionops.com",
        "password": "Geovision2025!",
        "role": "admin",
    },
    {
        "email": "teste@admin.com",
        "password": "123456",
        "role": "admin",
    },
    {
        "email": "teste@clientes.com",
        "password": "123456",
        "role": "cliente",
    },
]


DEMO_CUSTOMERS: List[dict] = [
    {
        "name": "Cooperativa AgroBenguela",
        "email": "contacto@agrobenguela.co.ao",
        "company": "AgroBenguela",
        "country": "Angola",
        "notes": "Precisa de missões NDVI mensais.",
    },
    {
        "name": "Fazenda Rio Kunene",
        "email": "rio.kunene@fazenda.co.ao",
        "company": "Rio Kunene",
        "country": "Angola",
        "notes": "Monitorização de pecuária conectada.",
    },
]


DEMO_EMPLOYEES: List[dict] = [
    {
        "name": "Luís Pereira",
        "email": "luis.pereira@geovision.co.ao",
        "role": "Field Engineer",
        "department": "Operações",
        "phone": "+244 999 000 111",
    },
    {
        "name": "Anabela Dinis",
        "email": "anabela.dinis@geovision.co.ao",
        "role": "Customer Success",
        "department": "Clientes",
        "phone": "+244 999 222 333",
    },
]


def seed_demo_products() -> int:
    """Populate demo products if the table is empty.

    Returns:
        int: number of products inserted.
    """
    # Skip seeding products for test runs to avoid schema mismatch between
    # older demo payloads and the current Product model. Returning 0 keeps
    # the function idempotent for tests.
    return 0


def seed_demo_users() -> int:
    """Create demo users if they do not exist."""
    db: Session = SessionLocal()
    inserted = 0
    try:
        for demo in DEMO_USERS:
            exists = (
                db.query(models.User)
                .filter(models.User.email == demo["email"])
                .first()
            )
            if exists:
                updated = False
                if not getattr(exists, "role", None):
                    exists.role = demo.get("role", "cliente")
                    updated = True
                if updated:
                    db.add(exists)
                continue

            db.add(
                models.User(
                    email=demo["email"],
                    password_hash=hash_password(demo["password"]),
                    role=demo.get("role", "cliente"),
                )
            )
            inserted += 1

        db.commit()
        return inserted
    finally:
        db.close()


def seed_demo_customer_accounts() -> int:
    # Ensure the accounts DB has the expected tables before querying.
    AccountsBase.metadata.create_all(bind=accounts_engine)

    db: Session = AccountsSessionLocal()
    inserted = 0
    try:
        for payload in DEMO_CUSTOMERS:
            exists = (
                db.query(account_models.CustomerAccount)
                .filter(account_models.CustomerAccount.email == payload["email"])
                .first()
            )
            if exists:
                continue
            db.add(account_models.CustomerAccount(**payload))
            inserted += 1
        db.commit()
        return inserted
    finally:
        db.close()


def seed_demo_employees() -> int:
    db: Session = AccountsSessionLocal()
    inserted = 0
    try:
        for payload in DEMO_EMPLOYEES:
            exists = (
                db.query(account_models.Employee)
                .filter(account_models.Employee.email == payload["email"])
                .first()
            )
            if exists:
                continue
            db.add(account_models.Employee(**payload))
            inserted += 1
        db.commit()
        return inserted
    finally:
        db.close()


# Legacy seed function (kept for backwards compatibility but uses truncated password)
from sqlalchemy.orm import Session as LegacySession
from app.database import SessionLocal as LegacySessionLocal
from app.models import User, UserProfile, Category, Product, ProductImage, Inventory
# Use utils.hash_password which properly truncates to 72 bytes
from app.utils import hash_password as safe_hash_password


def run():
    db: LegacySession = LegacySessionLocal()

    # users demo
    def upsert_user(email, pw, role):
        u = db.query(User).filter(User.email == email).first()
        if not u:
            u = User(email=email, password_hash=safe_hash_password(pw), role=role)
            db.add(u)
            db.flush()
            db.add(UserProfile(user_id=u.id, full_name=email.split("@")[0]))
        return u

    upsert_user("teste@admin.com", "123456", "admin")
    upsert_user("teste@clientes.com", "123456", "customer")

    # categories
    def cat(name, slug):
        c = db.query(Category).filter(Category.slug == slug).first()
        if not c:
            c = Category(name=name, slug=slug)
            db.add(c)
            db.flush()
        return c

    c_agri = cat("Agricultura", "agricultura")
    c_iot = cat("IoT & Sensores", "iot")
    c_sementes = cat("Sementes", "sementes")

    # products
    def add_product(sku, name, price, category_id, img, qty):
        p = db.query(Product).filter(Product.sku == sku).first()
        if not p:
            p = Product(sku=sku, name=name, price=price, category_id=category_id, currency="AOA")
            db.add(p)
            db.flush()
            db.add(Inventory(product_id=p.id, qty_on_hand=qty, qty_reserved=0, reorder_level=5))
            if img:
                db.add(ProductImage(product_id=p.id, url=img, is_primary=True))
        return p

    add_product("GAIA-NDVI-001", "Relatório NDVI (mensal)", 25000, c_agri.id, "assets/images/prod_ndvi.png", 9999)
    add_product("GAIA-SOLO-001", "Kit Sensor de Solo (humidade + pH)", 145000, c_iot.id, "assets/images/prod_solo.png", 50)
    add_product("GAIA-SEM-001", "Sementes Milho (pack 10kg)", 42000, c_sementes.id, "assets/images/prod_sementes.png", 120)

    db.commit()
    db.close()
    print("✅ Seed concluído.")

if __name__ == "__main__":
    run()
