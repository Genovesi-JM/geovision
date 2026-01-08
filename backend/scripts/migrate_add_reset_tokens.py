#!/usr/bin/env python3
"""Migration script: create reset_tokens table if missing.

Run this from the repository root with the project's venv activated:

    cd backend
    ./.venv/bin/python scripts/migrate_add_reset_tokens.py

This script is idempotent and safe to run multiple times.
"""
from datetime import datetime
from sqlalchemy import text
from app.database import engine

DDL = """
CREATE TABLE IF NOT EXISTS reset_tokens (
  id TEXT PRIMARY KEY,
  token TEXT NOT NULL UNIQUE,
  user_id TEXT NOT NULL,
  used INTEGER NOT NULL DEFAULT 0,
  expires_at DATETIME NOT NULL,
  created_at DATETIME NOT NULL
);
"""

def main():
    print('[migrate] creating reset_tokens table if not exists')
    with engine.begin() as conn:
        conn.execute(text(DDL))
    print('[migrate] done')

if __name__ == '__main__':
    main()
