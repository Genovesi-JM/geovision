from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import subprocess
import sys


def _run_alembic(
    backend_dir: Path,
    database_path: Path,
    command: str,
    revision: str,
) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path}"
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", command, revision],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def _columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info('{table_name}')")}


def test_organization_migration_backfills_links_roles_and_lifecycle(tmp_path):
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "organization-migration.sqlite3"
    _run_alembic(backend_dir, database_path, "upgrade", "identity_boundary_v1")

    owner_id = "40000000-0000-4000-8000-000000000001"
    member_id = "40000000-0000-4000-8000-000000000002"
    admin_id = "40000000-0000-4000-8000-000000000003"
    company_id = "40000000-0000-4000-8000-000000000010"
    linked_account_id = "40000000-0000-4000-8000-000000000020"
    orphan_account_id = "40000000-0000-4000-8000-000000000021"

    with sqlite3.connect(database_path) as connection:
        connection.executemany(
            """
            INSERT INTO users
                (id, email, password_hash, role, is_active, auth_generation,
                 created_at, updated_at)
            VALUES (?, ?, NULL, ?, 1, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            [
                (owner_id, "phase4-owner@example.test", "cliente"),
                (member_id, "phase4-member@example.test", "cliente"),
                (admin_id, "phase4-admin@example.test", "admin"),
            ],
        )
        connection.execute(
            """
            INSERT INTO companies
                (id, name, email, country, sectors, status, subscription_plan,
                 max_users, max_sites, max_storage_gb, current_users,
                 current_sites, storage_used_gb, created_at, updated_at)
            VALUES (?, 'Existing organization', 'phase4-owner@example.test',
                    'Angola', '[]', 'active', 'trial', 5, 10, 50, 0, 0, 0,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (company_id,),
        )
        connection.execute(
            """
            INSERT INTO company_users
                (id, company_id, user_id, email, name, role, is_active,
                 last_login, created_at)
            VALUES
                ('40000000-0000-4000-8000-000000000030', ?, ?,
                 'phase4-owner@example.test', 'Owner', 'owner', 1, NULL,
                 CURRENT_TIMESTAMP)
            """,
            (company_id, owner_id),
        )
        connection.executemany(
            """
            INSERT INTO accounts
                (id, name, sector_focus, entity_type, org_name, modules_enabled,
                 customer_type, dashboard_profile, use_cases,
                 onboarding_user_id, created_at, updated_at)
            VALUES (?, ?, 'agro', 'company', ?, '[]', 'business', 'business',
                    '[]', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            [
                (
                    linked_account_id,
                    "Existing workspace",
                    "Existing organization",
                    owner_id,
                ),
                (
                    orphan_account_id,
                    "Orphan workspace",
                    "Orphan organization",
                    None,
                ),
            ],
        )
        connection.executemany(
            """
            INSERT INTO account_members (account_id, user_id, role, created_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
            [
                (linked_account_id, owner_id, "owner"),
                (orphan_account_id, member_id, "operator"),
            ],
        )

    _run_alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert {
            "organization_type",
            "timezone",
        }.issubset(_columns(connection, "companies"))
        assert {"organization_id", "status"}.issubset(
            _columns(connection, "accounts")
        )
        assert {
            "status",
            "invited_by_user_id",
            "invited_at",
            "joined_at",
            "updated_at",
        }.issubset(_columns(connection, "account_members"))
        assert {
            "status",
            "invited_by_user_id",
            "invited_at",
            "joined_at",
            "updated_at",
        }.issubset(_columns(connection, "company_users"))
        assert "internal_role_assignments" in {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

        linked = connection.execute(
            "SELECT organization_id, status FROM accounts WHERE id = ?",
            (linked_account_id,),
        ).fetchone()
        assert linked == (company_id, "active")
        orphan_organization_id = connection.execute(
            "SELECT organization_id FROM accounts WHERE id = ?",
            (orphan_account_id,),
        ).fetchone()[0]
        assert orphan_organization_id != company_id
        assert connection.execute(
            "SELECT count(*) FROM companies WHERE id = ?",
            (orphan_organization_id,),
        ).fetchone() == (1,)
        assert connection.execute(
            """
            SELECT role, status, joined_at IS NOT NULL
            FROM account_members
            WHERE account_id = ? AND user_id = ?
            """,
            (orphan_account_id, member_id),
        ).fetchone() == ("manager", "active", 1)
        assert connection.execute(
            """
            SELECT role, status, is_active
            FROM company_users
            WHERE company_id = ? AND user_id = ?
            """,
            (orphan_organization_id, member_id),
        ).fetchone() == ("manager", "active", 1)
        assert connection.execute(
            """
            SELECT role, is_active FROM internal_role_assignments
            WHERE user_id = ?
            """,
            (admin_id,),
        ).fetchone() == ("GV_SUPER_ADMIN", 1)
        assert connection.execute(
            "SELECT current_users FROM companies WHERE id = ?",
            (company_id,),
        ).fetchone() == (1,)

    _run_alembic(
        backend_dir,
        database_path,
        "downgrade",
        "identity_boundary_v1",
    )
    with sqlite3.connect(database_path) as connection:
        assert "organization_id" not in _columns(connection, "accounts")
        assert "status" not in _columns(connection, "account_members")
        assert "status" not in _columns(connection, "company_users")
        assert "organization_type" not in _columns(connection, "companies")
        assert connection.execute("SELECT count(*) FROM accounts").fetchone() == (2,)
        assert connection.execute("SELECT count(*) FROM users").fetchone() == (3,)

    _run_alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT organization_id FROM accounts WHERE id = ?",
            (orphan_account_id,),
        ).fetchone() == (orphan_organization_id,)
        assert connection.execute(
            """
            SELECT count(*) FROM company_users
            WHERE company_id = ? AND user_id = ?
            """,
            (orphan_organization_id, member_id),
        ).fetchone() == (1,)
        assert connection.execute(
            """
            SELECT count(*) FROM internal_role_assignments
            WHERE user_id = ? AND role = 'GV_SUPER_ADMIN'
            """,
            (admin_id,),
        ).fetchone() == (1,)
