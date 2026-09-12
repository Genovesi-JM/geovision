"""Independent accounts database migrations; no application/settings imports.

Production execution receives the URL only through its protected environment.
Tests inject a disposable connection through Alembic's documented attributes.
Existing unversioned tables intentionally fail instead of being silently stamped.
"""

import os

from alembic import context
from sqlalchemy import create_engine, pool


def migrate(connection):
    context.configure(connection=connection, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()


provided_connection = context.config.attributes.get("connection")
if provided_connection is not None:
    migrate(provided_connection)
else:
    url = os.environ.get("ACCOUNTS_DATABASE_URL", "")
    if not url:
        raise RuntimeError("ACCOUNTS_DATABASE_URL is required for accounts migrations")
    if context.is_offline_mode():
        context.configure(url=url, literal_binds=True, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()
    else:
        engine = create_engine(url, poolclass=pool.NullPool, hide_parameters=True)
        try:
            with engine.connect() as connection:
                migrate(connection)
        finally:
            engine.dispose()
