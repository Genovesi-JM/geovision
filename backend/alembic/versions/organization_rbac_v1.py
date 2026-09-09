"""Link organizations/workspaces and add canonical membership RBAC.

Revision ID: organization_rbac_v1
Revises: identity_boundary_v1
"""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from alembic import context, op
import sqlalchemy as sa


revision = "organization_rbac_v1"
down_revision = "identity_boundary_v1"
branch_labels = None
depends_on = None


ACCOUNT_ORGANIZATION_FK = "fk_accounts_organization_id_companies"
ACCOUNT_ORGANIZATION_INDEX = "ix_accounts_organization_id"
ACCOUNT_INVITER_FK = "fk_account_members_invited_by_users"
COMPANY_INVITER_FK = "fk_company_users_invited_by_users"
INTERNAL_ROLE_USER_INDEX = "ix_internal_role_assignments_user_id"
INTERNAL_ROLE_UNIQUE = "uq_internal_role_user_role"
INTERNAL_ROLE_CHECK = "ck_internal_role_name"


def _canonical_customer_role(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"owner", "admin", "manager", "member", "viewer", "finance"}:
        return normalized
    if normalized == "operator":
        return "manager"
    if normalized in {"client", "cliente", "customer"}:
        return "member"
    return "viewer"


def _workspace_organization_id(account_id: str) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"geovision:organization:workspace:{account_id}",
        )
    )


def _backfill_organizations_and_memberships() -> None:
    connection = op.get_bind()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    accounts = connection.execute(
        sa.text(
            """
            SELECT id, name, org_name, sector_focus, onboarding_user_id,
                   created_at, updated_at
            FROM accounts
            ORDER BY created_at, id
            """
        )
    ).mappings()

    for account in accounts:
        organization_id = None
        if account["onboarding_user_id"]:
            candidate = connection.execute(
                sa.text(
                    """
                    SELECT company_id
                    FROM company_users
                    WHERE user_id = :user_id
                    ORDER BY CASE WHEN role = 'owner' THEN 0 ELSE 1 END,
                             created_at, id
                    LIMIT 1
                    """
                ),
                {"user_id": account["onboarding_user_id"]},
            ).first()
            organization_id = candidate[0] if candidate else None

        if organization_id is None:
            candidate = connection.execute(
                sa.text(
                    """
                    SELECT company_users.company_id
                    FROM account_members
                    JOIN company_users
                      ON company_users.user_id = account_members.user_id
                    WHERE account_members.account_id = :account_id
                    ORDER BY CASE WHEN account_members.role = 'owner' THEN 0 ELSE 1 END,
                             account_members.created_at,
                             company_users.created_at,
                             company_users.id
                    LIMIT 1
                    """
                ),
                {"account_id": account["id"]},
            ).first()
            organization_id = candidate[0] if candidate else None

        if organization_id is None:
            organization_id = _workspace_organization_id(account["id"])
            owner = connection.execute(
                sa.text(
                    """
                    SELECT users.email
                    FROM account_members
                    JOIN users ON users.id = account_members.user_id
                    WHERE account_members.account_id = :account_id
                    ORDER BY CASE WHEN account_members.role = 'owner' THEN 0 ELSE 1 END,
                             account_members.created_at,
                             users.id
                    LIMIT 1
                    """
                ),
                {"account_id": account["id"]},
            ).first()
            email = (
                owner[0]
                if owner
                else f"workspace-{organization_id}@invalid.geovision.local"
            )
            exists = connection.execute(
                sa.text("SELECT 1 FROM companies WHERE id = :id"),
                {"id": organization_id},
            ).first()
            if exists is None:
                connection.execute(
                    sa.text(
                        """
                        INSERT INTO companies
                            (id, name, tax_id, email, phone, address, country,
                             organization_type, timezone, sectors, status,
                             subscription_plan, max_users, max_sites,
                             max_storage_gb, current_users, current_sites,
                             storage_used_gb, created_at, updated_at)
                        VALUES
                            (:id, :name, NULL, :email, NULL, NULL, 'Angola',
                             'customer', 'UTC', :sectors, 'active', 'trial',
                             5, 10, 50, 0, 0, 0, :created_at, :updated_at)
                        """
                    ),
                    {
                        "id": organization_id,
                        "name": account["org_name"] or account["name"],
                        "email": email,
                        "sectors": f'["{account["sector_focus"]}"]',
                        "created_at": account["created_at"] or now,
                        "updated_at": account["updated_at"] or now,
                    },
                )

        connection.execute(
            sa.text(
                "UPDATE accounts SET organization_id = :organization_id "
                "WHERE id = :account_id"
            ),
            {"organization_id": organization_id, "account_id": account["id"]},
        )

        members = connection.execute(
            sa.text(
                """
                SELECT account_members.user_id, account_members.role,
                       account_members.created_at, users.email,
                       user_profiles.full_name
                FROM account_members
                JOIN users ON users.id = account_members.user_id
                LEFT JOIN user_profiles ON user_profiles.user_id = users.id
                WHERE account_members.account_id = :account_id
                ORDER BY account_members.created_at, account_members.user_id
                """
            ),
            {"account_id": account["id"]},
        ).mappings()
        for member in members:
            existing = connection.execute(
                sa.text(
                    """
                    SELECT id FROM company_users
                    WHERE company_id = :organization_id AND user_id = :user_id
                    """
                ),
                {
                    "organization_id": organization_id,
                    "user_id": member["user_id"],
                },
            ).first()
            if existing is None:
                connection.execute(
                    sa.text(
                        """
                        INSERT INTO company_users
                            (id, company_id, user_id, email, name, role,
                             is_active, status, invited_by_user_id, invited_at,
                             joined_at, last_login, created_at, updated_at)
                        VALUES
                            (:id, :organization_id, :user_id, :email, :name,
                             :role, :is_active, 'active', NULL, NULL,
                             :joined_at, NULL, :created_at, :updated_at)
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "organization_id": organization_id,
                        "user_id": member["user_id"],
                        "email": member["email"],
                        "name": member["full_name"],
                        "role": _canonical_customer_role(member["role"]),
                        "is_active": True,
                        "joined_at": member["created_at"] or now,
                        "created_at": member["created_at"] or now,
                        "updated_at": member["created_at"] or now,
                    },
                )

    connection.execute(
        sa.text(
            """
            UPDATE companies
            SET current_users = (
                SELECT count(*) FROM company_users
                WHERE company_users.company_id = companies.id
                  AND company_users.user_id IS NOT NULL
                  AND company_users.is_active = true
                  AND company_users.status = 'active'
            )
            """
        )
    )


def upgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError(
            "organization_rbac_v1 requires an online migration for safe "
            "organization/workspace backfill"
        )

    with op.batch_alter_table("companies") as batch:
        batch.add_column(
            sa.Column(
                "organization_type",
                sa.String(length=50),
                server_default="customer",
                nullable=False,
            )
        )
        batch.add_column(
            sa.Column(
                "timezone",
                sa.String(length=64),
                server_default="UTC",
                nullable=False,
            )
        )

    with op.batch_alter_table("accounts") as batch:
        batch.add_column(
            sa.Column("organization_id", sa.String(length=36), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "status",
                sa.String(length=20),
                server_default="active",
                nullable=False,
            )
        )

    with op.batch_alter_table("account_members") as batch:
        batch.add_column(
            sa.Column(
                "status",
                sa.String(length=20),
                server_default="active",
                nullable=False,
            )
        )
        batch.add_column(
            sa.Column("invited_by_user_id", sa.String(length=36), nullable=True)
        )
        batch.add_column(sa.Column("invited_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("joined_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))
        batch.create_foreign_key(
            ACCOUNT_INVITER_FK,
            "users",
            ["invited_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("company_users") as batch:
        batch.add_column(
            sa.Column(
                "status",
                sa.String(length=20),
                server_default="active",
                nullable=False,
            )
        )
        batch.add_column(
            sa.Column("invited_by_user_id", sa.String(length=36), nullable=True)
        )
        batch.add_column(sa.Column("invited_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("joined_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))
        batch.create_foreign_key(
            COMPANY_INVITER_FK,
            "users",
            ["invited_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.execute(
        sa.text(
            """
            UPDATE account_members
            SET role = CASE lower(trim(role))
                WHEN 'owner' THEN 'owner'
                WHEN 'admin' THEN 'admin'
                WHEN 'manager' THEN 'manager'
                WHEN 'operator' THEN 'manager'
                WHEN 'member' THEN 'member'
                WHEN 'client' THEN 'member'
                WHEN 'cliente' THEN 'member'
                WHEN 'customer' THEN 'member'
                WHEN 'finance' THEN 'finance'
                ELSE 'viewer'
            END,
            status = 'active',
            joined_at = created_at,
            updated_at = created_at
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE company_users
            SET role = CASE lower(trim(role))
                WHEN 'owner' THEN 'owner'
                WHEN 'admin' THEN 'admin'
                WHEN 'manager' THEN 'manager'
                WHEN 'operator' THEN 'manager'
                WHEN 'member' THEN 'member'
                WHEN 'client' THEN 'member'
                WHEN 'cliente' THEN 'member'
                WHEN 'customer' THEN 'member'
                WHEN 'finance' THEN 'finance'
                ELSE 'viewer'
            END,
            status = CASE
                WHEN is_active = false THEN 'suspended'
                WHEN user_id IS NULL THEN 'invited'
                ELSE 'active'
            END,
            invited_at = CASE WHEN user_id IS NULL THEN created_at ELSE NULL END,
            joined_at = CASE WHEN user_id IS NOT NULL THEN created_at ELSE NULL END,
            updated_at = created_at
            """
        )
    )

    _backfill_organizations_and_memberships()

    with op.batch_alter_table("account_members") as batch:
        batch.alter_column("updated_at", existing_type=sa.DateTime(), nullable=False)
    with op.batch_alter_table("company_users") as batch:
        batch.alter_column("updated_at", existing_type=sa.DateTime(), nullable=False)
    with op.batch_alter_table("accounts") as batch:
        batch.alter_column(
            "organization_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )
        batch.create_foreign_key(
            ACCOUNT_ORGANIZATION_FK,
            "companies",
            ["organization_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_index(
            ACCOUNT_ORGANIZATION_INDEX,
            ["organization_id"],
            unique=False,
        )

    op.create_table(
        "internal_role_assignments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column("assigned_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "role IN ('GV_SUPER_ADMIN', 'GV_OPERATIONS', 'GV_ANALYST', "
            "'GV_SUPPORT', 'GV_FINANCE', 'GV_INVENTORY', 'GV_SALES')",
            name=INTERNAL_ROLE_CHECK,
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "role", name=INTERNAL_ROLE_UNIQUE),
    )
    op.create_index(
        INTERNAL_ROLE_USER_INDEX,
        "internal_role_assignments",
        ["user_id"],
        unique=False,
    )
    connection = op.get_bind()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    admins = connection.execute(
        sa.text("SELECT id FROM users WHERE lower(trim(role)) = 'admin'")
    )
    for admin in admins:
        connection.execute(
            sa.text(
                """
                INSERT INTO internal_role_assignments
                    (id, user_id, role, is_active, assigned_by_user_id,
                     created_at, updated_at)
                VALUES
                    (:id, :user_id, 'GV_SUPER_ADMIN', :is_active, NULL,
                     :created_at, :updated_at)
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "user_id": admin[0],
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
        )


def downgrade() -> None:
    op.drop_index(
        INTERNAL_ROLE_USER_INDEX,
        table_name="internal_role_assignments",
    )
    op.drop_table("internal_role_assignments")

    with op.batch_alter_table("accounts") as batch:
        batch.drop_index(ACCOUNT_ORGANIZATION_INDEX)
        batch.drop_constraint(ACCOUNT_ORGANIZATION_FK, type_="foreignkey")
        batch.drop_column("status")
        batch.drop_column("organization_id")

    with op.batch_alter_table("company_users") as batch:
        batch.drop_constraint(COMPANY_INVITER_FK, type_="foreignkey")
        batch.drop_column("updated_at")
        batch.drop_column("joined_at")
        batch.drop_column("invited_at")
        batch.drop_column("invited_by_user_id")
        batch.drop_column("status")

    with op.batch_alter_table("account_members") as batch:
        batch.drop_constraint(ACCOUNT_INVITER_FK, type_="foreignkey")
        batch.drop_column("updated_at")
        batch.drop_column("joined_at")
        batch.drop_column("invited_at")
        batch.drop_column("invited_by_user_id")
        batch.drop_column("status")

    with op.batch_alter_table("companies") as batch:
        batch.drop_column("timezone")
        batch.drop_column("organization_type")
