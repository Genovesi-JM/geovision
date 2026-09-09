"""Add issuer-qualified external identity fields.

Revision ID: identity_boundary_v1
Revises: account_profiles_v1
"""

from datetime import datetime, timezone
import uuid

from alembic import context, op
import sqlalchemy as sa


revision = "identity_boundary_v1"
down_revision = "account_profiles_v1"
branch_labels = None
depends_on = None


GOOGLE_ISSUER = "https://accounts.google.com"
ISSUER_SUBJECT_INDEX = "ix_auth_identities_issuer_subject"
COMPANY_USER_USER_INDEX = "ix_company_users_user_id"
COMPANY_USER_USER_FK = "fk_company_users_user_id_users"
COMPANY_USER_MEMBERSHIP_UQ = "uq_company_users_company_user"
REFRESH_FAMILY_USER_INDEX = "ix_refresh_token_families_user_id"
REFRESH_FAMILY_IDENTITY_INDEX = "ix_refresh_token_families_auth_identity_id"
REFRESH_TOKEN_FAMILY_FK = "fk_refresh_tokens_family_id_refresh_token_families"
USER_EMAIL_NORMALIZED_INDEX = "ix_users_email_normalized"
ACCOUNT_ONBOARDING_USER_INDEX = "ix_accounts_onboarding_user_id"
ACCOUNT_ONBOARDING_USER_FK = "fk_accounts_onboarding_user_id_users"


def _preflight_identity_collisions() -> None:
    """Stop before any DDL when legacy data needs operator reconciliation."""

    connection = op.get_bind()
    invalid_user_ids = 0
    for row in connection.execute(sa.text("SELECT id FROM users")):
        raw_user_id = str(row[0] or "")
        try:
            canonical_user_id = str(uuid.UUID(raw_user_id))
        except (ValueError, AttributeError, TypeError):
            invalid_user_ids += 1
            continue
        if raw_user_id != canonical_user_id:
            invalid_user_ids += 1
    if invalid_user_ids:
        raise RuntimeError(
            "identity migration preflight failed: "
            f"{invalid_user_ids} user IDs are not canonical UUIDs"
        )

    duplicate_email = connection.execute(
        sa.text(
            """
            SELECT 1
            FROM users
            GROUP BY lower(trim(email))
            HAVING count(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicate_email:
        raise RuntimeError(
            "identity migration preflight failed: duplicate normalized user emails"
        )

    duplicate_company_membership = connection.execute(
        sa.text(
            """
            SELECT 1
            FROM company_users
            JOIN users
              ON lower(trim(users.email)) = lower(trim(company_users.email))
            GROUP BY company_users.company_id, users.id
            HAVING count(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicate_company_membership:
        raise RuntimeError(
            "identity migration preflight failed: duplicate company membership"
        )

    duplicate_google_subject = connection.execute(
        sa.text(
            """
            SELECT 1
            FROM auth_identities
            WHERE lower(trim(provider)) = 'google'
              AND provider_user_id IS NOT NULL
              AND trim(provider_user_id) <> ''
            GROUP BY provider_user_id
            HAVING count(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicate_google_subject:
        raise RuntimeError(
            "identity migration preflight failed: duplicate Google subjects"
        )

    blank_refresh_family = connection.execute(
        sa.text(
            """
            SELECT 1
            FROM refresh_tokens
            WHERE family_id IS NULL OR trim(family_id) = ''
            LIMIT 1
            """
        )
    ).first()
    if blank_refresh_family:
        raise RuntimeError(
            "identity migration preflight failed: blank refresh family IDs"
        )

    cross_user_refresh_family = connection.execute(
        sa.text(
            """
            SELECT 1
            FROM refresh_tokens
            GROUP BY family_id
            HAVING count(DISTINCT user_id) > 1
            LIMIT 1
            """
        )
    ).first()
    if cross_user_refresh_family:
        raise RuntimeError(
            "identity migration preflight failed: refresh family spans users"
        )


def upgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError(
            "identity_boundary_v1 requires an online migration so identity "
            "collision checks and compatibility backfills cannot be skipped"
        )
    _preflight_identity_collisions()

    # The historical column stored raw password-reset bearer secrets. Revoke
    # outstanding links at cutover; new application code stores only hashes in
    # the same column, avoiding a risky cross-database column rewrite.
    op.execute(sa.text("UPDATE reset_tokens SET used = true WHERE used = false"))

    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column(
                "auth_generation",
                sa.Integer(),
                server_default=sa.text("0"),
                nullable=False,
            )
        )

    with op.batch_alter_table("reset_tokens") as batch:
        batch.add_column(
            sa.Column(
                "auth_generation",
                sa.Integer(),
                server_default=sa.text("0"),
                nullable=False,
            )
        )

    # Fail closed when historical rows differ only by casing/whitespace. An
    # operator must reconcile that identity collision before the cutover. Add
    # this after SQLite's table-copying batch operation so it is not lost.
    op.create_index(
        USER_EMAIL_NORMALIZED_INDEX,
        "users",
        [sa.text("lower(trim(email))")],
        unique=True,
    )

    with op.batch_alter_table("accounts") as batch:
        batch.add_column(
            sa.Column("onboarding_user_id", sa.String(length=36), nullable=True)
        )
        batch.create_foreign_key(
            ACCOUNT_ONBOARDING_USER_FK,
            "users",
            ["onboarding_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index(
            ACCOUNT_ONBOARDING_USER_INDEX,
            ["onboarding_user_id"],
            unique=True,
        )

    with op.batch_alter_table("auth_identities") as batch:
        batch.add_column(sa.Column("issuer", sa.String(length=500), nullable=True))
        batch.add_column(sa.Column("subject", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("tenant_id", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("email_verified", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("last_login_at", sa.DateTime(), nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE auth_identities
            SET issuer = :google_issuer,
                subject = provider_user_id
            WHERE lower(trim(provider)) = 'google'
              AND provider_user_id IS NOT NULL
              AND trim(provider_user_id) <> ''
            """
        ).bindparams(google_issuer=GOOGLE_ISSUER)
    )

    with op.batch_alter_table("auth_identities") as batch:
        batch.create_index(
            ISSUER_SUBJECT_INDEX,
            ["issuer", "subject"],
            unique=True,
        )

    with op.batch_alter_table("company_users") as batch:
        batch.add_column(sa.Column("user_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            COMPANY_USER_USER_FK,
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_index(COMPANY_USER_USER_INDEX, ["user_id"], unique=False)

    # Freeze only the pre-cutover, unique legacy mapping snapshot. The runbook
    # requires registration to be paused and these candidates to be reviewed
    # because historical registration did not prove mailbox ownership. Runtime
    # authorization never performs this email binding again.
    op.execute(
        sa.text(
            """
            UPDATE company_users
            SET user_id = (
                SELECT users.id
                FROM users
                WHERE lower(trim(users.email)) = lower(trim(company_users.email))
                LIMIT 1
            )
            WHERE user_id IS NULL
              AND 1 = (
                  SELECT count(*)
                  FROM users
                  WHERE lower(trim(users.email)) = lower(trim(company_users.email))
              )
            """
        )
    )

    # Preserve the old, implicit Company-email access once, under the runbook's
    # registration freeze and operator-reviewed snapshot. Only unambiguous
    # one-company/one-user pairs are materialized; runtime code never repeats
    # this email inference.
    connection = op.get_bind()
    candidates = connection.execute(
        sa.text(
            """
            SELECT companies.id AS company_id,
                   companies.email AS company_email,
                   users.id AS user_id
            FROM companies
            JOIN users
              ON lower(trim(users.email)) = lower(trim(companies.email))
            WHERE NOT EXISTS (
                SELECT 1 FROM company_users
                WHERE company_users.company_id = companies.id
                  AND company_users.user_id = users.id
            )
              AND 1 = (
                SELECT count(*) FROM users candidate_users
                WHERE lower(trim(candidate_users.email)) =
                      lower(trim(companies.email))
              )
              AND 1 = (
                SELECT count(*) FROM companies candidate_companies
                WHERE lower(trim(candidate_companies.email)) =
                      lower(trim(companies.email))
              )
            """
        )
    ).mappings()
    created_at = datetime.now(timezone.utc).replace(tzinfo=None)
    for candidate in candidates:
        connection.execute(
            sa.text(
                """
                INSERT INTO company_users
                    (id, company_id, user_id, email, name, role,
                     is_active, last_login, created_at)
                VALUES
                    (:id, :company_id, :user_id, :email, NULL, 'owner',
                     :is_active, NULL, :created_at)
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "company_id": candidate["company_id"],
                "user_id": candidate["user_id"],
                "email": candidate["company_email"],
                "is_active": True,
                "created_at": created_at,
            },
        )

    # This denormalized field is used by the admin dashboard. Reconcile it
    # after both direct legacy links and materialized Company-owner rows.
    op.execute(
        sa.text(
            """
            UPDATE companies
            SET current_users = (
                SELECT count(*)
                FROM company_users
                WHERE company_users.company_id = companies.id
                  AND company_users.user_id IS NOT NULL
                  AND company_users.is_active = true
            )
            """
        )
    )

    with op.batch_alter_table("company_users") as batch:
        batch.create_unique_constraint(
            COMPANY_USER_MEMBERSHIP_UQ,
            ["company_id", "user_id"],
        )

    op.create_table(
        "refresh_token_families",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("auth_identity_id", sa.String(length=36), nullable=True),
        sa.Column("identity_provider", sa.String(length=50), nullable=False),
        sa.Column("identity_issuer", sa.String(length=500), nullable=True),
        sa.Column("identity_subject", sa.String(length=500), nullable=False),
        sa.Column(
            "auth_generation",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("compromised_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["auth_identity_id"],
            ["auth_identities.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        REFRESH_FAMILY_USER_INDEX,
        "refresh_token_families",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        REFRESH_FAMILY_IDENTITY_INDEX,
        "refresh_token_families",
        ["auth_identity_id"],
        unique=False,
    )
    op.execute(
        sa.text(
            """
            INSERT INTO refresh_token_families
                (id, user_id, auth_identity_id, identity_provider,
                 identity_issuer, identity_subject, auth_generation, revoked_at,
                 compromised_at, expires_at, created_at)
            SELECT family_id, min(user_id), NULL, 'internal', NULL,
                   min(user_id), 0, NULL, NULL, max(expires_at), min(created_at)
            FROM refresh_tokens
            GROUP BY family_id
            """
        )
    )
    with op.batch_alter_table("refresh_tokens") as batch:
        batch.create_foreign_key(
            REFRESH_TOKEN_FAMILY_FK,
            "refresh_token_families",
            ["family_id"],
            ["id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("oauth_states") as batch:
        batch.add_column(sa.Column("provider", sa.String(length=30), nullable=True))
        batch.add_column(sa.Column("code_verifier", sa.String(length=128), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("oauth_states") as batch:
        batch.drop_column("code_verifier")
        batch.drop_column("provider")

    with op.batch_alter_table("refresh_tokens") as batch:
        batch.drop_constraint(REFRESH_TOKEN_FAMILY_FK, type_="foreignkey")
    op.drop_index(
        REFRESH_FAMILY_IDENTITY_INDEX,
        table_name="refresh_token_families",
    )
    op.drop_index(
        REFRESH_FAMILY_USER_INDEX,
        table_name="refresh_token_families",
    )
    op.drop_table("refresh_token_families")

    with op.batch_alter_table("company_users") as batch:
        batch.drop_constraint(COMPANY_USER_MEMBERSHIP_UQ, type_="unique")
        batch.drop_index(COMPANY_USER_USER_INDEX)
        batch.drop_constraint(COMPANY_USER_USER_FK, type_="foreignkey")
        batch.drop_column("user_id")

    with op.batch_alter_table("auth_identities") as batch:
        batch.drop_index(ISSUER_SUBJECT_INDEX)
        batch.drop_column("last_login_at")
        batch.drop_column("email_verified")
        batch.drop_column("tenant_id")
        batch.drop_column("subject")
        batch.drop_column("issuer")

    with op.batch_alter_table("accounts") as batch:
        batch.drop_index(ACCOUNT_ONBOARDING_USER_INDEX)
        batch.drop_constraint(ACCOUNT_ONBOARDING_USER_FK, type_="foreignkey")
        batch.drop_column("onboarding_user_id")

    op.drop_index(USER_EMAIL_NORMALIZED_INDEX, table_name="users")
    with op.batch_alter_table("reset_tokens") as batch:
        batch.drop_column("auth_generation")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("auth_generation")
