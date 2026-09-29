from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

# check_same_thread=False is required for SQLite with a threaded server.
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    # Import models so they register on Base.metadata before create_all.
    from app.models import request, user  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_request_columns()


def _ensure_request_columns() -> None:
    """Add newer columns to an existing requests table (lightweight dev migration)."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "requests" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("requests")}
    wanted = {
        "requester_id": "ALTER TABLE requests ADD COLUMN requester_id INTEGER",
        "requester_name": "ALTER TABLE requests ADD COLUMN requester_name VARCHAR(255)",
        "priority": "ALTER TABLE requests ADD COLUMN priority VARCHAR(16)",
        "owner": "ALTER TABLE requests ADD COLUMN owner VARCHAR(255)",
        "notes": "ALTER TABLE requests ADD COLUMN notes TEXT",
    }
    statements = [sql for col, sql in wanted.items() if col not in existing]
    if not statements:
        return
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
