"""
FraudShield AI - FastAPI application entrypoint (PART 7, Week 7 Day 1)
==========================================================================
Run:  uvicorn app.main:app --reload   (from inside backend/, venv active)
Docs: http://localhost:8000/docs (Swagger UI, auto-generated)
"""
from contextlib import asynccontextmanager
import datetime
import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config.settings import settings
from app.database import Base, engine
from app.ml.model_service import ModelService
from app.routes import alerts, audit, auth, dashboard, reports, transactions, users, cases, profiles, merchants, feedback, monitoring, graph
from app.models.model_version import ModelVersion
from app.utils.error_handlers import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.utils.logging_config import RequestLoggingMiddleware
from app.utils.rate_limit import limiter
from app.websocket.socket_server import socket_app


def _sync_missing_columns() -> None:
    """Add columns that exist on the models but not yet in the database.

    `Base.metadata.create_all` creates missing *tables* but never adds columns
    to tables that already exist, and the bulk-ingested databases were seeded
    from a template file rather than through Alembic, so they have no
    `alembic_version` and cannot be brought forward with `alembic upgrade head`
    (it would try to replay every migration from scratch).

    This closes that gap for the dev/SQLite path. On Postgres, run the real
    Alembic revision instead -- these are the same changes:
      alembic/versions/c3d81f4a2b90_audit_log_detail.py
    """
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        present = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in present:
                continue
            ddl = (f'ALTER TABLE {table.name} ADD COLUMN "{col.name}" '
                   f'{col.type.compile(dialect=engine.dialect)}')
            if not col.nullable:
                ddl += " NOT NULL DEFAULT ''" if col.type.python_type is str else " NOT NULL DEFAULT 0"
            with engine.begin() as conn:
                conn.execute(text(ddl))
            logging.getLogger(__name__).info(
                "added missing column %s.%s", table.name, col.name)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables if missing (Alembic manages real migrations;
    # this call is a convenience for a fresh dev DB) and load the ML model
    # exactly once so /transactions/predict never pays model-load latency.
    Base.metadata.create_all(bind=engine)
    _sync_missing_columns()
    ModelService.load()
    # Synchronize the currently loaded artifact into the model registry for a fresh dev DB.
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        meta = ModelService.metadata()
        version = meta.get("version", "live-hybrid-v1")
        metrics = meta.get("metrics", {})
        # train_live_model.py nests precision/recall/f1 under the `review`
        # operating point rather than at the top level, so reading them from
        # the top level wrote NULLs into the registry. Use the review point
        # (the threshold the live pipeline actually reviews at).
        review = metrics.get("review", {}) or {}
        existing = db.query(ModelVersion).filter(ModelVersion.version == version).first()
        fields = dict(
            precision=review.get("precision"), recall=review.get("recall"),
            f1_score=review.get("f1"), roc_auc=metrics.get("roc_auc"),
            pr_auc=metrics.get("pr_auc"), is_active=True, status="production",
            dataset_version=meta.get("dataset_version"),
            feature_version=meta.get("feature_version"),
            threshold=meta.get("threshold"),
            artifact_path=str(ModelService._models_root() / "live-v1"),
        )
        if existing is None:
            db.add(ModelVersion(
                version=version,
                trained_at=datetime.datetime.fromisoformat(meta["trained_at"].replace("Z", "+00:00"))
                if meta.get("trained_at") else datetime.datetime.now(datetime.timezone.utc),
                **fields,
            ))
        else:
            # Backfill rows seeded before the nested-metrics fix.
            for k, v in fields.items():
                if getattr(existing, k) is None and v is not None:
                    setattr(existing, k, v)
        db.commit()
    finally:
        db.close()

    # Start the built-in synthetic feed so a signed-in dashboard has live
    # traffic from the moment it loads, without anyone having to start
    # scripts/simulator.py by hand. Uses the real scoring pipeline.
    if settings.LIVE_FEED_ENABLED:
        from app.services.live_feed import live_feed
        live_feed.start()

    try:
        yield
    finally:
        if settings.LIVE_FEED_ENABLED:
            from app.services.live_feed import live_feed
            await live_feed.stop()


app = FastAPI(
    title=settings.APP_NAME,
    description="Intelligent Online Transaction Fraud Detection and Real-Time "
                 "Monitoring System -- B.Tech Final Year Academic Prototype. "
                 "Uses public/synthetic data only.",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,  # explicit allow-list, never "*"
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(transactions.router, prefix=settings.API_V1_PREFIX)
app.include_router(alerts.router, prefix=settings.API_V1_PREFIX)
app.include_router(dashboard.router, prefix=settings.API_V1_PREFIX)
app.include_router(reports.router, prefix=settings.API_V1_PREFIX)
app.include_router(audit.router, prefix=settings.API_V1_PREFIX)
app.include_router(users.router, prefix=settings.API_V1_PREFIX)
app.include_router(cases.router, prefix=settings.API_V1_PREFIX)
app.include_router(profiles.router, prefix=settings.API_V1_PREFIX)
app.include_router(merchants.router, prefix=settings.API_V1_PREFIX)
app.include_router(feedback.router, prefix=settings.API_V1_PREFIX)
app.include_router(monitoring.router, prefix=settings.API_V1_PREFIX)
app.include_router(graph.router, prefix=settings.API_V1_PREFIX)

# Mount the Socket.IO ASGI app so real-time events share the same server.
app.mount("/socket.io", socket_app)
