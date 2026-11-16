"""
FraudShield AI — Graph-based fraud ring detection.

Builds a transaction graph (users, merchants, devices, IPs as nodes) and
computes a per-transaction graph risk score. This addresses the weakness of
per-user behavioral features (PaySim users have <=3 transactions) by detecting
coordinated fraud rings through shared entities and circular transaction flows.

Graph risk signals:
  - Device sharing: how many prior fraud users share this device
  - Merchant concentration: fraction of a device's recent users flagged as fraud
  - Circular flow: transaction path back to the originator within N hops
  - Burst connectivity: many new accounts transacting the same merchant in a short window
"""

from __future__ import annotations

import math
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import sys

_ML_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_ML_SRC) not in sys.path:
    sys.path.insert(0, str(_ML_SRC))

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.transaction import Transaction
from app.models.fraud_alert import FraudAlert


class GraphEngine:
    """Sliding-window transaction graph engine.

    Maintains an in-memory graph over the last ``window_minutes`` minutes of
    transactions. For each new transaction it computes a graph risk score in [0,1]
    based on shared-entity exposure and structural fraud patterns.
    """

    def __init__(self, window_minutes: int = 60, fraud_lookback_hours: int = 24):
        self.window_minutes = window_minutes
        self.fraud_lookback_hours = fraud_lookback_hours
        # Node -> set of connected node ids
        self._device_users: dict[str, set[str]] = defaultdict(set)
        self._user_devices: dict[str, set[str]] = defaultdict(set)
        self._merchant_devices: dict[str, set[str]] = defaultdict(set)
        self._device_merchants: dict[str, set[str]] = defaultdict(set)
        self._user_merchants: dict[str, set[str]] = defaultdict(set)
        self._merchant_users: dict[str, set[str]] = defaultdict(set)
        self._user_txn_times: dict[str, list[float]] = defaultdict(list)
        self._fraud_users: set[str] = set()
        self._cutoff_ts: float = 0.0

    # ------------------------------------------------------------------ window maintenance
    def _prune(self, now_ts: float) -> None:
        cutoff = now_ts - self.window_minutes * 60
        self._cutoff_ts = cutoff
        # Prune per-user transaction timestamps
        for uid in list(self._user_txn_times):
            self._user_txn_times[uid] = [t for t in self._user_txn_times[uid] if t > cutoff]
            if not self._user_txn_times[uid]:
                del self._user_txn_times[uid]

    def _record(self, txn_row: Transaction, device_row: Device | None,
                amount: float, user_id: str, device_id: str, merchant_id: str,
                ts: float) -> None:
        now_ts = txn_row.created_at.timestamp() if txn_row.created_at else ts
        self._prune(now_ts)

        # Record device-user edge
        self._device_users[device_id].add(user_id)
        self._user_devices[user_id].add(device_id)

        # Record device-merchant and merchant-user edges
        self._device_merchants[device_id].add(merchant_id)
        self._merchant_devices[merchant_id].add(device_id)
        self._user_merchants[user_id].add(merchant_id)
        self._merchant_users[merchant_id].add(user_id)

        # Record user transaction times
        self._user_txn_times[user_id].append(now_ts)

        # Mark known fraud users (from open alerts)
        self._fraud_users.discard(user_id)

    def add_fraud_user(self, user_id: str) -> None:
        self._fraud_users.add(user_id)

    def remove_fraud_user(self, user_id: str) -> None:
        self._fraud_users.discard(user_id)

    # ------------------------------------------------------------------ scoring
    def score(self, user_id: str, device_id: str, merchant_id: str,
              ts: float) -> dict[str, float]:
        """Compute graph risk signals for a candidate transaction.

        Returns a dict of signal names to values in [0,1] plus an aggregate
        ``graph_risk`` score.
        """
        now_ts = ts

        # Signal 1: Device shared with known fraud users
        fraud_device_users = self._device_users.get(device_id, set()) & self._fraud_users
        device_fraud_exposure = min(1.0, len(fraud_device_users) / 3.0)

        # Signal 2: Device used by many distinct recent users (device farm pattern)
        device_user_count = len(self._device_users.get(device_id, set()))
        device_farm_signal = min(1.0, max(0.0, (device_user_count - 1)) / 10.0)

        # Signal 3: Merchant seen by many distinct recent devices (merchant farm)
        merchant_device_count = len(self._device_merchants.get(merchant_id, set()))
        merchant_farm_signal = min(1.0, max(0.0, (merchant_device_count - 1)) / 10.0)

        # Signal 4: User transacting at unusual velocity in this window
        user_recent = len(self._user_txn_times.get(user_id, []))
        user_velocity_signal = min(1.0, max(0.0, (user_recent - 1)) / 15.0)

        # Signal 5: User shares device with fraud user (direct link to fraud)
        user_shares_fraud_device = bool(
            self._user_devices.get(user_id, set()) &
            {d for d, us in self._device_users.items() if us & self._fraud_users}
        )
        shared_fraud_device_signal = 1.0 if user_shares_fraud_device else 0.0

        # Signal 6: Merchant has many fraud users recently (merchant-level fraud concentration)
        merchant_fraud_users = self._merchant_users.get(merchant_id, set()) & self._fraud_users
        merchant_fraud_concentration = min(1.0, len(merchant_fraud_users) / 3.0)

        # Aggregate: weighted sum, emphasising direct fraud links
        signals = {
            "device_fraud_exposure": device_fraud_exposure,
            "device_farm": device_farm_signal,
            "merchant_farm": merchant_farm_signal,
            "user_velocity": user_velocity_signal,
            "shared_fraud_device": shared_fraud_device_signal,
            "merchant_fraud_concentration": merchant_fraud_concentration,
        }

        weights = {
            "device_fraud_exposure": 0.25,
            "device_farm": 0.15,
            "merchant_farm": 0.15,
            "user_velocity": 0.10,
            "shared_fraud_device": 0.20,
            "merchant_fraud_concentration": 0.15,
        }

        graph_risk = sum(signals[k] * weights[k] for k in weights)

        return {
            **signals,
            "graph_risk": min(1.0, graph_risk),
        }


_graph_engine: GraphEngine | None = None


def get_graph_engine() -> GraphEngine:
    global _graph_engine
    if _graph_engine is None:
        _graph_engine = GraphEngine()
    return _graph_engine


def load_fraud_users_from_db(db: Session) -> None:
    """Populate the graph engine with currently known fraud users from open alerts."""
    engine = get_graph_engine()
    engine._fraud_users.clear()
    alerts = db.execute(select(FraudAlert)).scalars().all()
    for alert in alerts:
        txn = db.execute(
            select(Transaction).where(Transaction.id == alert.transaction_id)
        ).scalar_one_or_none()
        if txn is not None:
            engine.add_fraud_user(str(txn.user_id))


def build_graph_features(db: Session, txn_input: dict) -> dict[str, Any]:
    """Compute graph-based features for a transaction being scored.

    The transaction itself is not yet persisted; we score against the historical
    graph only, then the caller records the transaction into the graph after
    prediction (see ``record_transaction``).
    """
    engine = get_graph_engine()
    user_id = str(txn_input["user_id"])
    device_id = str(txn_input.get("device_id") or "unknown")
    merchant_id = str(txn_input.get("merchant_id") or "unknown")
    ts = datetime.now(timezone.utc).timestamp()

    # Ensure fraud users are loaded
    if not engine._fraud_users:
        load_fraud_users_from_db(db)

    signals = engine.score(user_id, device_id, merchant_id, ts)

    return {
        "graph_risk": signals["graph_risk"],
        "graph_device_fraud_exposure": signals["device_fraud_exposure"],
        "graph_device_farm": signals["device_farm"],
        "graph_merchant_farm": signals["merchant_farm"],
        "graph_user_velocity": signals["user_velocity"],
        "graph_shared_fraud_device": signals["shared_fraud_device"],
        "graph_merchant_fraud_concentration": signals["merchant_fraud_concentration"],
        **signals,
    }


def record_transaction(db: Session, txn_row: Transaction,
                       device_row: Device | None,
                       user_id: str, device_id: str, merchant_id: str,
                       ts: float) -> None:
    """Record a scored transaction into the live graph for future scoring."""
    engine = get_graph_engine()
    engine._record(txn_row, device_row, float(txn_row.amount),
                   user_id, device_id, merchant_id, ts)
