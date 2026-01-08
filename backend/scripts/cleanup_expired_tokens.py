#!/usr/bin/env python3
"""Cleanup script that removes expired reset_tokens and oauth_states.

Run periodically (cron, systemd timer) or on-demand:

  cd backend
  ./.venv/bin/python scripts/cleanup_expired_tokens.py

"""
from datetime import datetime
from app.database import engine
from sqlalchemy import text

DELETE_SQL = '''
DELETE FROM reset_tokens WHERE expires_at < :now;
DELETE FROM oauth_states WHERE expires_at < :now;
'''


def main():
    now = datetime.utcnow().isoformat(sep=' ')
    print('[cleanup] deleting expired tokens older than', now)
    with engine.begin() as conn:
        for stmt in DELETE_SQL.strip().splitlines():
            if not stmt.strip():
                continue
            conn.execute(text(stmt), {"now": now})
    print('[cleanup] done')


if __name__ == '__main__':
    main()
