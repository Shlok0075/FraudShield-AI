"""FraudShield AI - background auto-investigation sweeper.

The inline path (services/prediction_pipeline.py) investigates every new REVIEW/BLOCK alert as it
is created. This sweeper is the safety net behind it:

  * alerts still `open` because the inline investigation failed (or predate it) are investigated;
  * open cases nobody has touched for AUTO_ESCALATE_AFTER_HOURS are bumped to high priority.

It runs in a worker thread so it never stalls the event loop, in small batches so it never holds
the database for long, and it is idempotent: investigating moves an alert out of `open`, and a case
a human has decided is never touched.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.database import SessionLocal
from app.models.case import CaseNote, FraudCase
from app.models.fraud_alert import FraudAlert
from app.services.audit_service import log_action
from app.services.investigation_service import get_system_user, run_investigation

log = logging.getLogger("fraudshield.auto_investigator")


def _utcnow_naive() -> datetime:
    # Timestamps are stored as naive UTC.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def escalate_stale_cases(db: Session, limit: int = 100) -> int:
    """Bump long-unattended open cases from low/medium to high priority (once)."""
    cutoff = _utcnow_naive() - timedelta(hours=settings.AUTO_ESCALATE_AFTER_HOURS)
    stale = db.execute(
        select(FraudCase)
        .where(FraudCase.status == "open", FraudCase.priority.in_(("low", "medium")),
               FraudCase.updated_at <= cutoff)
        .order_by(FraudCase.updated_at.asc()).limit(limit)
    ).scalars().all()
    if not stale:
        return 0
    system = get_system_user(db)
    for case in stale:
        case.priority = "high"
        db.add(CaseNote(case_id=case.id, author_id=system.id,
                        note=f"Priority raised to high automatically: no analyst action for "
                             f"{settings.AUTO_ESCALATE_AFTER_HOURS:g}h."))
    db.commit()
    for case in stale:
        log_action(db, system.id, "case.auto_escalate", "case", case.id)
    return len(stale)


def sweep_once(db: Session, *, limit: int | None = None, min_age_s: float = 10.0) -> dict:
    """Investigate up to `limit` open alerts older than `min_age_s`, then escalate stale cases.

    `min_age_s` keeps the sweeper from racing the inline path that is still working on an alert
    it just created.
    """
    limit = limit or settings.AUTO_INVESTIGATE_BATCH
    cutoff = _utcnow_naive() - timedelta(seconds=min_age_s)
    ids = db.execute(
        select(FraudAlert.id)
        .where(FraudAlert.status == "open", FraudAlert.created_at <= cutoff)
        .order_by(FraudAlert.id.asc()).limit(limit)
    ).scalars().all()

    counts = {"AUTO_CLEAR": 0, "AUTO_BLOCK": 0, "REVIEW": 0}
    skipped = errors = 0
    for alert_id in ids:
        try:
            result = run_investigation(db, alert_id, emit=False)
        except Exception as exc:  # noqa: BLE001 - one bad alert must not stop the batch
            db.rollback()
            errors += 1
            log.warning("auto-investigation of alert %s failed: %s", alert_id, exc)
            continue
        if "skipped" in result:
            skipped += 1
        else:
            counts[result["applied"]] = counts.get(result["applied"], 0) + 1
    escalated = escalate_stale_cases(db)
    return {"examined": len(ids), "applied": counts, "skipped": skipped, "errors": errors,
            "stale_escalated": escalated}


class AutoInvestigator:
    """Periodic sweeper task, started and stopped with the app (like the live feed)."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self.running = False
        self.last_run: str | None = None
        self.last_result: dict | None = None
        self.last_error: str | None = None

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run(), name="fraudshield-auto-investigator")
        self.running = True

    async def stop(self) -> None:
        self.running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None

    def status(self) -> dict:
        return {"running": self.running and self._task is not None and not self._task.done(),
                "interval_seconds": settings.AUTO_INVESTIGATE_INTERVAL_SECONDS,
                "auto_resolve_enabled": settings.AUTO_RESOLVE_ENABLED,
                "shadow_mode": settings.AUTO_RESOLVE_SHADOW,
                "last_run": self.last_run, "last_result": self.last_result,
                "last_error": self.last_error}

    @staticmethod
    def _tick() -> dict:
        db = SessionLocal()
        try:
            return sweep_once(db)
        finally:
            db.close()

    async def _run(self) -> None:
        interval = max(1.0, float(settings.AUTO_INVESTIGATE_INTERVAL_SECONDS))
        while True:
            try:
                self.last_result = await asyncio.to_thread(self._tick)
                self.last_run = datetime.now(timezone.utc).isoformat()
                self.last_error = None
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - the loop must survive any single failure
                self.last_error = f"{type(exc).__name__}: {exc}"
                log.warning("auto-investigation sweep failed: %s", exc)
            await asyncio.sleep(interval)


auto_investigator = AutoInvestigator()
