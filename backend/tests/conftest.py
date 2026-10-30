"""
FraudShield AI - pytest fixtures (PART 15 / Week 13 Day 3)
=============================================================
Integration tests use an in-memory SQLite DB instead of a separate test
Postgres instance -- documented tradeoff: SQLite is fast and needs no
external service for CI, at the cost of not exercising Postgres-specific
SQL. All app code that touches raw SQL functions (see
app/services/feature_engineering.py's docstring) was written to be
portable across both.
"""
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Force the app's module-level engine (created at import time from
# settings.DATABASE_URL) onto an in-memory SQLite DB so tests need no
# external Postgres. Must be set BEFORE importing app.main / app.config.settings.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

# The app lifespan starts the built-in live feed. In tests that background
# writer would run for the whole session against a *different* in-memory DB
# than the one under test, injecting non-determinism into every count-based
# assertion. Feed behaviour is covered explicitly in test_live_feed.py.
os.environ.setdefault("LIVE_FEED_ENABLED", "false")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.utils.rate_limit import limiter  # noqa: E402

TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture()
def db_session():
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    limiter.reset()  # each test starts with a fresh rate-limit bucket
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def admin_token(client):
    client.post("/api/v1/auth/register", json={
        "email": "admin@fraudshield.ai", "password": "StrongPass123!", "role": "admin",
    })
    resp = client.post("/api/v1/auth/login", json={
        "email": "admin@fraudshield.ai", "password": "StrongPass123!",
    })
    return resp.json()["access_token"]


@pytest.fixture()
def user_token(client):
    client.post("/api/v1/auth/register", json={
        "email": "viewer@fraudshield.ai", "password": "StrongPass123!", "role": "user",
    })
    resp = client.post("/api/v1/auth/login", json={
        "email": "viewer@fraudshield.ai", "password": "StrongPass123!",
    })
    return resp.json()["access_token"]
