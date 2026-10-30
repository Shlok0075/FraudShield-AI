"""FraudShield AI live behavioral feature adapter.

The legacy implementation projected a single ``risk_intensity`` value onto
anonymized V1-V28 columns. This module removes that dependency. It replays
persisted transaction history through the same point-in-time ``FeatureEngine``
used by the ML training pipeline and computes the current transaction's real
behavioral features before the current transaction is inserted.

For the academic prototype, history is replayed from the database on each
prediction. This favors correctness and restart-safe behavior over throughput.
A production system would replace this with a persistent/streaming feature
store.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.transaction import Transaction

# Make the shared training/inference feature engine importable.
_ML_SRC = Path(__file__).resolve().parents[3] / "ml" / "src"
if str(_ML_SRC) not in sys.path:
    sys.path.insert(0, str(_ML_SRC))

from fraudpipe.features import FeatureEngine, Txn  # noqa: E402

# Must match ml/src/paysim_ingest.UNKNOWN_MERCHANT_KEY: the key standing in for the
# NULL / "unknown" merchant bucket in paysim_merchant_counts.
UNKNOWN_MERCHANT_KEY = -1

LOCATION_COORDS = {
    "mumbai": (19.0760, 72.8777), "delhi": (28.6139, 77.2090),
    "bengaluru": (12.9716, 77.5946), "bangalore": (12.9716, 77.5946),
    "pune": (18.5204, 73.8567), "chennai": (13.0827, 80.2707),
    "hyderabad": (17.3850, 78.4867), "kolkata": (22.5726, 88.3639),
    "ahmedabad": (23.0225, 72.5714), "lagos": (6.5244, 3.3792),
    "reykjavik": (64.1466, -21.9426), "minsk": (53.9006, 27.5590),
    "unknown-vpn-exit": (0.0, 0.0),
}


def _coords(location: str | None) -> tuple[float | None, float | None]:
    if not location:
        return None, None
    text = location.strip().lower()
    if text == "unknown-vpn-exit":
        return None, None
    if text in LOCATION_COORDS:
        return LOCATION_COORDS[text]
    # Also accept a safe "lat,lon" representation for simulator/testing data.
    try:
        lat, lon = [float(x.strip()) for x in text.split(",", 1)]
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon
    except (ValueError, TypeError):
        pass
    return None, None


def _ts(dt: datetime | None) -> float:
    if dt is None:
        return datetime.now(timezone.utc).timestamp()
    aware = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return aware.timestamp()


def build_features(db: Session, txn_input: dict) -> dict:
    """Build the shared v1 behavioral feature vector from prior DB history.

    The current transaction is intentionally NOT inserted into the replay
    state before ``features()`` is called, preventing current-row leakage.

    Cost. ``FeatureEngine.features()`` reads only the current user's ``_UserState``
    and the current counterparty's ``_CpState`` -- no other actor's state is ever
    consulted. Replaying the whole ``transactions`` table on every request is
    therefore wasted work: against the 6.36M-row PaySim corpus it materialised
    6.36M rows and timed the request out. This loads only the current user's rows
    (a small, indexed set) and takes the counterparty's prior count as a SQL
    COUNT, which is the same number the full replay would have produced.
    """
    engine = FeatureEngine(groups=("core", "device_geo"), label_delay_s=86400, prior_fraud_rate=0.001)

    user_id = txn_input["user_id"]
    merchant_id = txn_input.get("merchant_id")
    # The engine keys counterparties by `str(merchant_id or "unknown")`.
    cp_key = str(merchant_id or "unknown")

    history = db.execute(
        select(Transaction, Device.device_id)
        .join(Device, Device.id == Transaction.device_id, isouter=True)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.created_at.asc(), Transaction.id.asc())
    ).all()

    # Replay only history; analyst-confirmed labels are not available in the
    # legacy schema yet, so label=None keeps fraud-rate features at the prior.
    replayed_cp = 0
    for txn, device_id in history:
        lat, lon = _coords(txn.location)
        row_cp = str(txn.merchant_id or "unknown")
        if row_cp == cp_key:
            replayed_cp += 1
        engine.update(Txn(
            ts=_ts(txn.created_at),
            user_id=str(txn.user_id),
            counterparty_id=row_cp,
            amount=float(txn.amount),
            txn_type=txn.payment_method or "card",
            device_id=device_id,
            lat=lat,
            lon=lon,
        ), label=None)

    # Counterparty prior count. `n` is absolute, so subtract the rows above that
    # already contributed to this counterparty.
    #
    # The bulk corpus is immutable once ingested, so the per-merchant counts are
    # precomputed by ml/src/paysim_ingest.py. Computing them with a live COUNT
    # instead costs ~1.5s, because every bulk row shares the NULL/"unknown"
    # merchant bucket. Falls back to COUNT(*) where no rollup exists.
    cp_key_id = UNKNOWN_MERCHANT_KEY if merchant_id is None else int(merchant_id)
    cp_total = None
    try:
        cp_total = db.execute(
            text("SELECT prior_count FROM paysim_merchant_counts WHERE merchant_id = :mid"),
            {"mid": cp_key_id},
        ).scalar()
    except SQLAlchemyError:
        cp_total = None
    if cp_total is None:
        cp_where = (Transaction.merchant_id.is_(None) if merchant_id is None
                    else Transaction.merchant_id == merchant_id)
        cp_total = db.execute(select(func.count(Transaction.id)).where(cp_where)).scalar() or 0
    engine.seed_counterparty_count(cp_key, max(int(cp_total) - replayed_cp, 0))

    lat, lon = _coords(txn_input.get("location"))
    now_ts = datetime.now(timezone.utc).timestamp()
    current = Txn(
        ts=now_ts,
        user_id=str(txn_input["user_id"]),
        counterparty_id=cp_key,
        amount=float(txn_input["amount"]),
        txn_type=txn_input.get("payment_method") or "card",
        device_id=str(txn_input["device_id"]),
        lat=lat,
        lon=lon,
    )
    features = engine.features(current)
    features["_raw"] = {
        "feature_version": "v1",
        "location": txn_input.get("location"),
        "device_id": txn_input.get("device_id"),
    }
    return features
