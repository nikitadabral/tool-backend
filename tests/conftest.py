import os
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure the backend package root (containing `app`) is importable.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.session import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import request, request_audit, user  # noqa: E402,F401


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    settings = SimpleNamespace(
        outbound_webhook_url=None,
        outbound_webhook_timeout_seconds=5.0,
        outbound_webhook_secret=None,
    )
    monkeypatch.setattr("app.api.routes.intake.get_settings", lambda: settings)
    app.dependency_overrides[get_db] = override_get_db
    # No context manager: skip lifespan so the real app.db is left untouched.
    yield TestClient(app)
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
