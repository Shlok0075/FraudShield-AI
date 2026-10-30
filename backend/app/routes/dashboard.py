"""
FraudShield AI - Dashboard analytics routes (PART 12.10-12.16, Weeks 9-10, 14)
==============================================================================
Scaling note. The original implementation pulled every row into Python
(`db.query(Transaction).all()`, then counted in a defaultdict), which is O(rows) in
both time and memory. Against the 6.36M-row PaySim corpus that means materialising
6.36M ORM objects per request.

Two changes make this viable at corpus scale:

1. All aggregation is pushed into SQL. Endpoints that touch small tables
   (`fraud_predictions`, `devices`, `merchants`) run plain GROUP BY.

2. The PaySim corpus is immutable once ingested, and SQLite must scan the fact
   table for any live aggregate over it -- measured at 6.36M rows:
       COUNT(*)                     0.4s
       GROUP BY step                8.4s
       GROUP BY txn_type            9.4s
       strftime bucket + 2 joins    31.5s
       COUNT(DISTINCT name_orig)  262.5s
       COUNT(DISTINCT name_dest)  142.6s
   So `ml/src/paysim_ingest.py` precomputes those into small rollup tables
   (`paysim_rollup_hourly`, `paysim_rollup_type`, `paysim_ingest_meta`) and these
   handlers read those. Re-run with `paysim_ingest.py --refresh-rollups` after any
   data change. Live model predictions are still counted per request, driven from
   the small `fraud_predictions` table so cost scales with predictions rather than
   with transactions.

Ground truth vs. predictions. The KPIs aggregate `fraud_predictions.risk_level`
(model output). PaySim's `isFraud` is ground truth and lives in the
`paysim_*` tables, so it is surfaced as a separate, explicitly-labelled
`paysim_*` / `true_fraud` series rather than being mixed into model numbers.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, inspect, text
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.ml.model_service import ModelService
from app.models.fraud_alert import FraudAlert
from app.models.fraud_prediction import FraudPrediction
from app.models.merchant import Merchant
from app.models.transaction import Transaction
from app.models.user import User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

RISK_LEVELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
PAYSIM_EPOCH = 1_704_067_200   # must match fraudpipe.datasets.PAYSIM_EPOCH

# The PaySim training corpus is bulk-loaded into `transactions` under a NEGATIVE
# id range (see ml/src/paysim_ingest.py --id-base) so it can never collide with
# rows the running app creates. That gives us a free, indexed discriminator for
# "is this a live transaction?" without a schema change.
#
# The headline KPIs deliberately count ONLY live traffic, so Total Transactions
# starts at 0 and climbs as the live feed runs -- a dashboard that opens on
# 6,362,820 tells an operator nothing about whether the pipeline is alive.
# Corpus figures stay available, explicitly labelled, under the `paysim_*` keys
# and /dashboard/paysim-by-type.
LIVE_ONLY = Transaction.id >= 0

# Cached per-process: the paysim_* tables only exist in bulk-ingested databases and
# never appear or disappear while the app is running.
_HAS_PAYSIM: bool | None = None


def has_paysim(db: Session) -> bool:
    """True when this database has been bulk-ingested with the PaySim corpus.

    Uses SQLAlchemy's inspector rather than `sqlite_master` so this also works on
    Postgres, which `settings.DATABASE_URL` defaults to in production.
    """
    global _HAS_PAYSIM
    if _HAS_PAYSIM is None:
        try:
            insp = inspect(db.get_bind())
            _HAS_PAYSIM = (insp.has_table("paysim_rollup_hourly")
                           and insp.has_table("paysim_ingest_meta"))
        except Exception:
            _HAS_PAYSIM = False
    return _HAS_PAYSIM


def _paysim_meta(db: Session) -> dict[str, str]:
    return dict(db.execute(text("SELECT key, value FROM paysim_ingest_meta")).all())


def _step_datetime(step: int, epoch: int) -> datetime:
    return datetime.fromtimestamp(epoch + step * 3600, tz=timezone.utc)


@router.get("/kpis")
def kpis(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Live-pipeline KPIs: counts per risk level in one grouped pass.

    Every figure here is scoped to live transactions (`id >= 0`), so the numbers
    start at zero and track the feed. PaySim's 6.36M-row corpus is training
    data, not live traffic, and is reported separately under `paysim_*`.
    """
    level_counts = dict(
        db.query(FraudPrediction.risk_level, func.count(FraudPrediction.id))
        .join(Transaction, Transaction.id == FraudPrediction.transaction_id)
        .filter(LIVE_ONLY)
        .group_by(FraudPrediction.risk_level)
        .all()
    )
    scored = sum(level_counts.values())
    fraud_count = level_counts.get("CRITICAL", 0)
    active_alerts = db.query(func.count(FraudAlert.id)) \
        .filter(FraudAlert.status == "open").scalar() or 0
    high_risk_users = db.query(func.count(func.distinct(Transaction.user_id))).join(
        FraudPrediction, FraudPrediction.transaction_id == Transaction.id
    ).filter(FraudPrediction.risk_level == "CRITICAL", LIVE_ONLY).scalar() or 0

    total = db.query(func.count(Transaction.id)).filter(LIVE_ONLY).scalar() or 0
    payload = {
        "total_transactions": total,
        "fraud_count": fraud_count,
        "suspicious_count": level_counts.get("MEDIUM", 0) + level_counts.get("HIGH", 0),
        "safe_count": level_counts.get("LOW", 0),
        "fraud_rate": round(fraud_count / scored, 4) if scored else 0.0,
        "active_alerts": active_alerts,
        "high_risk_users": high_risk_users,
        "scored_transactions": scored,
    }

    # Ground-truth PaySim totals, from the ingest-time rollup. Deliberately kept out
    # of the prediction fields above: these are labels, not model output.
    if has_paysim(db):
        meta = _paysim_meta(db)
        gt = int(meta.get("rows", 0))
        gt_fraud = int(meta.get("fraud", 0))
        payload["paysim_total"] = gt
        payload["paysim_fraud"] = gt_fraud
        payload["paysim_fraud_rate"] = round(gt_fraud / gt, 6) if gt else 0.0
        payload["paysim_users"] = int(meta.get("unique_users", 0))
        payload["paysim_counterparties"] = int(meta.get("unique_counterparties", 0))
    return payload


@router.get("/trends")
def trends(granularity: str = "day", db: Session = Depends(get_db),
           current_user: User = Depends(get_current_user)):
    """LIVE transaction volume over time.

    Scoped to live transactions (`id >= 0`) so this lines up with the KPI cards
    and starts empty, filling in as the feed runs. The corpus series is a
    separate, explicitly-labelled view at /dashboard/corpus-trends.
    """
    fmt = "%Y-%m-%d" if granularity == "day" else "%Y-%m-%d %H:00"
    rows = db.execute(text(f"""
        SELECT strftime('{fmt}', t.created_at) AS bucket,
               COUNT(*) AS transactions,
               COALESCE(SUM(CASE WHEN f.risk_level = 'CRITICAL' THEN 1 ELSE 0 END), 0) AS fraud
        FROM transactions t
        LEFT JOIN fraud_predictions f ON f.transaction_id = t.id
        WHERE t.id >= 0
        GROUP BY bucket
        ORDER BY bucket
    """)).all()
    return {"granularity": granularity, "scope": "live",
            "series": [{"bucket": r[0], "transactions": r[1], "fraud": r[2]} for r in rows]}


@router.get("/corpus-trends")
def corpus_trends(granularity: str = "day", db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    """The PaySim training corpus over time, from the ingest rollup.

    Kept separate from /trends so a 6.36M-row historical series is never mixed
    into the live dashboard. `transactions`/`true_fraud` come from
    `paysim_rollup_hourly` (743 rows), not the 6.36M-row fact table.
    """
    fmt = "%Y-%m-%d" if granularity == "day" else "%Y-%m-%d %H:00"

    if not has_paysim(db):
        return {"granularity": granularity, "scope": "corpus", "available": False, "series": []}

    meta = _paysim_meta(db)
    epoch = int(meta.get("epoch", PAYSIM_EPOCH))

    buckets: dict[str, dict] = {}
    for step, n, fraud in db.execute(text(
            "SELECT step, transactions, fraud FROM paysim_rollup_hourly ORDER BY step")):
        key = _step_datetime(step, epoch).strftime(fmt)
        b = buckets.setdefault(key, {"transactions": 0, "true_fraud": 0})
        b["transactions"] += n
        b["true_fraud"] += fraud

    series = [{"bucket": k, "transactions": v["transactions"], "true_fraud": v["true_fraud"]}
              for k, v in sorted(buckets.items())]
    return {"granularity": granularity, "scope": "corpus", "available": True, "series": series}


@router.get("/risk-distribution")
def risk_distribution(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    counts = dict(
        db.query(FraudPrediction.risk_level, func.count(FraudPrediction.id))
        .join(Transaction, Transaction.id == FraudPrediction.transaction_id)
        .filter(LIVE_ONLY)
        .group_by(FraudPrediction.risk_level)
        .all()
    )
    return [{"label": level, "value": counts.get(level, 0)} for level in RISK_LEVELS]


@router.get("/geographic")
def geographic(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Live transactions grouped by location.

    Groups on the bare column and maps NULL to "Unknown" afterwards: wrapping the
    column in COALESCE(...) makes the expression non-indexable, which turned this
    into a 6.36M-row table scan (8.6s) instead of an index scan.
    """
    rows = db.query(Transaction.location, func.count(Transaction.id)) \
        .filter(LIVE_ONLY).group_by(Transaction.location).all()
    out = [{"label": r[0] or "Unknown", "value": r[1]} for r in rows]
    return sorted(out, key=lambda d: -d["value"])


@router.get("/device-activity")
def device_activity(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.models.device import Device

    label = func.coalesce(Device.device_type, "unknown")
    rows = db.query(label, func.count(Device.id)).group_by(label).all()
    return [{"label": r[0], "value": r[1]} for r in rows]


@router.get("/merchant-risk")
def merchant_risk(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = db.query(Merchant.name, Merchant.risk_score) \
        .order_by(Merchant.risk_score.desc()).limit(10).all()
    return [{"label": r[0], "value": r[1]} for r in rows]


@router.get("/paysim-by-type")
def paysim_by_type(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Ground-truth fraud by PaySim transaction type, from the ingest rollup."""
    if not has_paysim(db):
        return {"available": False, "series": []}
    rows = db.execute(text("""
        SELECT txn_type, transactions, fraud, amount, fraud_amount
        FROM paysim_rollup_type ORDER BY transactions DESC
    """)).all()
    return {
        "available": True,
        "series": [
            {"label": r[0], "value": r[1], "fraud": r[2],
             "amount": float(r[3] or 0), "fraud_amount": float(r[4] or 0)}
            for r in rows
        ],
    }


@router.get("/model-info")
def model_info(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    meta = ModelService.metadata()
    metrics = meta.get("metrics", {})
    # train_live_model.py stores precision/recall/f1 per *operating point*
    # (`review` and `block`), not at the top level, because a single
    # precision/recall pair is meaningless without the threshold that produced
    # it -- which is also why the two points differ so much here (0.18/0.91 at
    # review vs 0.93/0.18 at block). Reading them from the top level silently
    # yielded 0.0 for all three, which looked like a broken model next to a
    # healthy ROC-AUC. Report the review point as the headline and expose both.
    review = metrics.get("review", {}) or {}
    block = metrics.get("block", {}) or {}
    return {
        "version": meta.get("version", "unknown"),
        "trained_at": meta.get("trained_at", ""),
        "precision": review.get("precision", 0.0),
        "recall": review.get("recall", 0.0),
        "f1": review.get("f1", 0.0),
        "review_threshold": review.get("threshold"),
        "block_precision": block.get("precision"),
        "block_recall": block.get("recall"),
        "block_f1": block.get("f1"),
        "block_threshold": block.get("threshold"),
        "fraud_test": metrics.get("fraud_test"),
        "test_rows": metrics.get("test_rows"),
        "roc_auc": metrics.get("roc_auc", 0.0),
        "pr_auc": metrics.get("pr_auc", 0.0),
        "predictions_served": db.query(func.count(FraudPrediction.id)).scalar() or 0,
    }
