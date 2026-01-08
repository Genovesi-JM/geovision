def init_db():
    """Deprecated: use Alembic migrations instead of create_all."""
    print("Use 'alembic upgrade head' to create/update the schema. This script no longer calls create_all().")


if __name__ == "__main__":
    init_db()
