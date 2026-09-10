#!/usr/bin/env python3
"""Explicit CLI for the local-only Phase 33 synthetic portfolio seed."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import database  # noqa: E402
from app.phase33_demo import (  # noqa: E402
    PHASE33_DEMO_NOTICE,
    Phase33DemoSeedError,
    seed_phase33_demo,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create the local-only, credential-free Phase 33 synthetic portfolio."
    )
    parser.add_argument(
        "--confirm-synthetic-demo",
        action="store_true",
        help="Acknowledge that every created record is synthetic demonstration data.",
    )
    parser.add_argument(
        "--attach-user-email",
        metavar="EMAIL",
        help=(
            "Attach one existing active local password account by exact canonical "
            "email; the command never creates or changes credentials."
        ),
    )
    args = parser.parse_args(argv)
    if not args.confirm_synthetic_demo:
        parser.error("--confirm-synthetic-demo is required")

    database.init_db_engine()
    if database.SessionLocal is None:
        raise RuntimeError("Database session factory is unavailable")
    db = database.SessionLocal()
    try:
        result = seed_phase33_demo(db, attach_user_email=args.attach_user_email)
        db.commit()
    except Phase33DemoSeedError as exc:
        db.rollback()
        print(f"Phase 33 demo seed refused: {exc}", file=sys.stderr)
        return 2
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(PHASE33_DEMO_NOTICE)
    print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
