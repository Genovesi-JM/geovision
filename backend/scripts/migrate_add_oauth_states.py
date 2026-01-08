#!/usr/bin/env python3
"""Migration script: create oauth_states table if missing.

Run from the backend/ folder with the venv active:

  ./.venv/bin/python scripts/migrate_add_oauth_states.py

"""
from sqlalchemy import text
from app.database import engine

DDL = """
CREATE TABLE IF NOT EXISTS oauth_states (
  id TEXT PRIMARY KEY,
  state TEXT NOT NULL UNIQUE,
  used INTEGER NOT NULL DEFAULT 0,
  expires_at DATETIME NOT NULL,
  created_at DATETIME NOT NULL
);
"""

def main():
    print('[migrate] creating oauth_states table if not exists')
    with engine.begin() as conn:
        conn.execute(text(DDL))
    print('[migrate] done')

if __name__ == '__main__':
    main()
