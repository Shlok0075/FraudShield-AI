"""
Point-in-time behavioral feature engine (feature version "v1").

ONE implementation is used for offline training and for live inference:
    * training  : iterate the time-sorted dataset, calling ``process(txn, label)``
    * inference : warm the state with ``update`` (history replay) then ``features``

Leakage rules enforced here (and covered by tests):
  1. Features for a transaction are computed from state built ONLY from earlier
     transactions; the transaction itself is added afterwards (``update``).
  2. Fraud labels are never visible immediately. A label becomes usable only
     ``label_delay_s`` seconds after the transaction it belongs to (fraud is
     confirmed late in reality). Until then it does not affect
     ``user_fraud_rate`` / ``counterparty_fraud_rate``.
  3. Nothing here reads the current row's label.

Feature groups
  core        : needs only user, counterparty, amount, timestamp  (works on PaySim)
  device_geo  : needs device_id and lat/lon (live/simulated data only; PaySim has neither)
  balance     : needs the origin/destination balances before and after the transaction. A bank
                always knows these at scoring time, so this group is legitimate in production; on
                PaySim they are simulator artefacts that make the benchmark much easier (see
                docs/paysim_evaluation.md). Stateless: computed from the transaction row only.
"""
from __future__ import annotations

import heapq
import math
from collections import deque
from dataclasses import dataclass

FEATURE_VERSION = "v1"

DAY_S = 86400
HOUR_S = 3600
NO_HISTORY_GAP_S = 30 * DAY_S          # time_since_last_txn_s for a user's first txn
UNUSUAL_HOURS = frozenset({0, 1, 2, 3, 4, 5})   # static, documented rule (UTC)
GEO_CHANGE_KM = 50.0                   # location_change threshold

CORE_FEATURES = [
    "amount", "log_amount",
    "user_txn_count_prior", "is_first_txn",
    "amount_vs_user_avg", "amount_zscore",
    "txn_count_1m", "txn_count_5m", "txn_count_1h", "txn_count_24h",
    "amount_sum_1h", "amount_sum_24h",
    "time_since_last_txn_s", "account_age_s",
    "hour_of_day", "day_of_week", "is_weekend", "unusual_hour",
    "counterparty_txn_count_prior",
    "user_fraud_rate_prior", "counterparty_fraud_rate_prior",
]
DEVICE_GEO_FEATURES = [
    "new_device", "known_device_count",
    "location_change", "distance_from_prev_km", "implied_speed_kmh",
]
CATEGORICAL_FEATURES = ["txn_type"]
BALANCE_FEATURES = [
    "orig_balance_error", "dest_balance_error", "orig_emptied",
    "dest_balance_unchanged", "amount_to_orig_balance", "orig_balance_missing",
]
GROUPS = {"core": CORE_FEATURES, "device_geo": DEVICE_GEO_FEATURES, "balance": BALANCE_FEATURES}

FEATURE_DESCRIPTIONS = {
    "amount": "Transaction amount.",
    "log_amount": "log(1 + amount).",
    "user_txn_count_prior": "Number of earlier transactions by this user.",
    "is_first_txn": "1 if the user has no earlier transaction.",
    "amount_vs_user_avg": "amount / user's mean prior amount (1.0 when no history).",
    "amount_zscore": "(amount - prior mean) / prior std; 0 when fewer than 2 prior txns or zero variance.",
    "txn_count_1m": "User transactions in the previous 60 s.",
    "txn_count_5m": "User transactions in the previous 5 min.",
    "txn_count_1h": "User transactions in the previous hour.",
    "txn_count_24h": "User transactions in the previous 24 h.",
    "amount_sum_1h": "Total amount the user sent in the previous hour.",
    "amount_sum_24h": "Total amount the user sent in the previous 24 h.",
    "time_since_last_txn_s": "Seconds since the user's previous txn (capped at 30 days; 30 days if none).",
    "account_age_s": "Seconds since the user's first observed txn (0 if none). Observation-window age, not true account age.",
    "hour_of_day": "Hour 0-23 (UTC).",
    "day_of_week": "0=Monday..6=Sunday.",
    "is_weekend": "1 if Saturday/Sunday.",
    "unusual_hour": "1 if hour is 00:00-05:59 (static rule, not per-user).",
    "counterparty_txn_count_prior": "Earlier transactions received by this counterparty/merchant.",
    "user_fraud_rate_prior": "Smoothed fraud rate of the user's earlier txns whose label is already MATURE (see label_delay_s).",
    "counterparty_fraud_rate_prior": "Same, for the counterparty/merchant.",
    "new_device": "1 if the device was never seen for this user before (device_geo group).",
    "known_device_count": "Distinct devices previously seen for the user (device_geo group).",
    "location_change": f"1 if previous location is > {GEO_CHANGE_KM:.0f} km away (device_geo group).",
    "distance_from_prev_km": "Haversine km from user's previous txn location (device_geo group).",
    "implied_speed_kmh": "distance_from_prev_km / hours since previous txn (device_geo group).",
    "orig_balance_error": "old_org - amount - new_org. 0 when the sender's balance moved by exactly the amount (balance group).",
    "dest_balance_error": "old_dest + amount - new_dest. 0 when the receiver was credited exactly the amount (balance group).",
    "orig_emptied": "1 if the sender's account was drained to 0 by this transaction (balance group).",
    "dest_balance_unchanged": "1 if the receiver's balance did not change although amount > 0 (balance group).",
    "amount_to_orig_balance": "amount / (old_org + 1): share of the sender's balance being moved (balance group).",
    "orig_balance_missing": "1 if the sender's opening balance is 0 (balance group).",
    "txn_type": "Categorical transaction type (one-hot encoded in preprocessing).",
}


@dataclass
class Txn:
    ts: float                    # epoch seconds
    user_id: str
    counterparty_id: str
    amount: float
    txn_type: str | None = None
    device_id: str | None = None
    lat: float | None = None
    lon: float | None = None
    old_org: float | None = None     # sender balance before / after (balance group)
    new_org: float | None = None
    old_dest: float | None = None    # receiver balance before / after (balance group)
    new_dest: float | None = None


class _UserState:
    __slots__ = ("n", "mean", "m2", "first_ts", "last_ts", "recent",
                 "devices", "last_lat", "last_lon", "lab_n", "lab_fraud")

    def __init__(self):
        self.n = 0
        self.mean = 0.0
        self.m2 = 0.0
        self.first_ts = None
        self.last_ts = None
        self.recent: deque = deque()          # (ts, amount) within last 24h
        self.devices: set = set()
        self.last_lat = None
        self.last_lon = None
        self.lab_n = 0
        self.lab_fraud = 0


class _CpState:
    __slots__ = ("n", "lab_n", "lab_fraud")

    def __init__(self):
        self.n = 0
        self.lab_n = 0
        self.lab_fraud = 0


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class FeatureEngine:
    def __init__(self, groups=("core",), label_delay_s: float = DAY_S,
                 prior_fraud_rate: float = 0.001, smoothing_m: float = 20.0):
        unknown = set(groups) - set(GROUPS)
        if unknown:
            raise ValueError(f"unknown feature groups: {unknown}")
        self.groups = tuple(groups)
        self.label_delay_s = label_delay_s
        self.prior_fraud_rate = prior_fraud_rate
        self.smoothing_m = smoothing_m
        self._users: dict[str, _UserState] = {}
        self._cps: dict[str, _CpState] = {}
        self._pending: list = []              # heap of (mature_ts, seq, user, cp, label)
        self._seq = 0

    # ---- schema -------------------------------------------------------
    @property
    def feature_names(self) -> list[str]:
        return [f for g in self.groups for f in GROUPS[g]]

    def params(self) -> dict:
        return {"feature_version": FEATURE_VERSION, "groups": list(self.groups),
                "label_delay_s": self.label_delay_s, "prior_fraud_rate": self.prior_fraud_rate,
                "smoothing_m": self.smoothing_m, "unusual_hours": sorted(UNUSUAL_HOURS),
                "geo_change_km": GEO_CHANGE_KM}

    # ---- label maturation ----------------------------------------------
    def _mature(self, now_ts: float) -> None:
        h = self._pending
        while h and h[0][0] <= now_ts:
            _, _, uid, cid, label = heapq.heappop(h)
            self._apply_label(uid, cid, label)

    def _apply_label(self, uid, cid, label) -> None:
        u = self._users.setdefault(uid, _UserState())
        c = self._cps.setdefault(cid, _CpState())
        u.lab_n += 1
        c.lab_n += 1
        if label:
            u.lab_fraud += 1
            c.lab_fraud += 1

    def _rate(self, fraud: int, n: int) -> float:
        m = self.smoothing_m
        return (fraud + m * self.prior_fraud_rate) / (n + m)

    def register_label(self, txn: Txn, label: int, known_at: float) -> None:
        """Feedback path: an analyst confirmed `label` for `txn` at time `known_at`."""
        self._seq += 1
        heapq.heappush(self._pending, (known_at, self._seq, txn.user_id, txn.counterparty_id, int(label)))

    # ---- features (READ-ONLY w.r.t. behavioral state) -------------------
    def features(self, t: Txn) -> dict:
        self._mature(t.ts)
        u = self._users.get(t.user_id)
        c = self._cps.get(t.counterparty_id)
        n = u.n if u else 0
        f: dict = {"txn_type": t.txn_type}
        f["amount"] = float(t.amount)
        f["log_amount"] = math.log1p(max(t.amount, 0.0))
        f["user_txn_count_prior"] = n
        f["is_first_txn"] = int(n == 0)
        f["amount_vs_user_avg"] = (t.amount / u.mean) if (n >= 1 and u.mean > 0) else 1.0
        if n >= 2:
            std = math.sqrt(u.m2 / n)
            f["amount_zscore"] = (t.amount - u.mean) / std if std > 0 else 0.0
        else:
            f["amount_zscore"] = 0.0
        c1 = c5 = ch = c24 = 0
        s1h = s24 = 0.0
        if u:
            for ts, amt in u.recent:
                dt = t.ts - ts
                if dt < 0 or dt > DAY_S:
                    continue
                c24 += 1
                s24 += amt
                if dt <= HOUR_S:
                    ch += 1
                    s1h += amt
                    if dt <= 300:
                        c5 += 1
                        if dt <= 60:
                            c1 += 1
        f.update(txn_count_1m=c1, txn_count_5m=c5, txn_count_1h=ch, txn_count_24h=c24,
                 amount_sum_1h=s1h, amount_sum_24h=s24)
        f["time_since_last_txn_s"] = (min(max(t.ts - u.last_ts, 0.0), NO_HISTORY_GAP_S)
                                      if (u and u.last_ts is not None) else float(NO_HISTORY_GAP_S))
        f["account_age_s"] = max(t.ts - u.first_ts, 0.0) if (u and u.first_ts is not None) else 0.0
        hour = int((t.ts // HOUR_S) % 24)
        dow = int((t.ts // DAY_S + 3) % 7)      # epoch day 0 was a Thursday
        f.update(hour_of_day=hour, day_of_week=dow, is_weekend=int(dow >= 5),
                 unusual_hour=int(hour in UNUSUAL_HOURS))
        f["counterparty_txn_count_prior"] = c.n if c else 0
        f["user_fraud_rate_prior"] = self._rate(u.lab_fraud, u.lab_n) if u else self.prior_fraud_rate
        f["counterparty_fraud_rate_prior"] = self._rate(c.lab_fraud, c.lab_n) if c else self.prior_fraud_rate
        if "device_geo" in self.groups:
            self._device_geo(t, u, f)
        if "balance" in self.groups:
            self._balance(t, f)
        return f

    @staticmethod
    def _balance(t: Txn, f: dict) -> None:
        nan = float("nan")
        if t.old_org is None or t.new_org is None:
            f.update(orig_balance_error=nan, orig_emptied=nan, amount_to_orig_balance=nan,
                     orig_balance_missing=nan)
        else:
            f["orig_balance_error"] = t.old_org - t.amount - t.new_org
            f["orig_emptied"] = int(t.new_org == 0 and t.old_org > 0)
            f["amount_to_orig_balance"] = t.amount / (t.old_org + 1.0)
            f["orig_balance_missing"] = int(t.old_org == 0)
        if t.old_dest is None or t.new_dest is None:
            f.update(dest_balance_error=nan, dest_balance_unchanged=nan)
        else:
            f["dest_balance_error"] = t.old_dest + t.amount - t.new_dest
            f["dest_balance_unchanged"] = int(t.new_dest == t.old_dest and t.amount > 0)

    def _device_geo(self, t: Txn, u, f: dict) -> None:
        nan = float("nan")
        if t.device_id is None:
            f["new_device"] = nan
        else:
            f["new_device"] = int(not (u and t.device_id in u.devices))
        f["known_device_count"] = len(u.devices) if u else 0
        if t.lat is None or t.lon is None or not u or u.last_lat is None:
            f.update(location_change=nan if t.lat is None else 0, distance_from_prev_km=nan,
                     implied_speed_kmh=nan)
            return
        d = haversine_km(u.last_lat, u.last_lon, t.lat, t.lon)
        hrs = max((t.ts - u.last_ts) / HOUR_S, 1 / 3600)
        f.update(location_change=int(d > GEO_CHANGE_KM), distance_from_prev_km=d,
                 implied_speed_kmh=d / hrs)

    # ---- state update ---------------------------------------------------
    def seed_counterparty_count(self, counterparty_id: str, n: int) -> None:
        """Seed a counterparty's prior-transaction count without replaying its rows.

        ``_CpState`` carries only ``n``, ``lab_n`` and ``lab_fraud``. When history is
        replayed with ``label=None`` (the live serving path in
        ``app/services/feature_engineering.py``) no labels are registered, so the
        counterparty state reduces to a single counter and can be supplied by a SQL
        COUNT instead of materialising every matching row. ``n`` is an absolute value,
        so callers must pass the true prior count for the counterparty.
        """
        self._cps.setdefault(str(counterparty_id), _CpState()).n = int(n)

    def update(self, t: Txn, label: int | None = None) -> None:
        u = self._users.setdefault(t.user_id, _UserState())
        c = self._cps.setdefault(t.counterparty_id, _CpState())
        u.n += 1
        delta = t.amount - u.mean
        u.mean += delta / u.n
        u.m2 += delta * (t.amount - u.mean)
        if u.first_ts is None:
            u.first_ts = t.ts
        u.last_ts = t.ts
        u.recent.append((t.ts, t.amount))
        while u.recent and t.ts - u.recent[0][0] > DAY_S:
            u.recent.popleft()
        if t.device_id is not None:
            u.devices.add(t.device_id)
        if t.lat is not None and t.lon is not None:
            u.last_lat, u.last_lon = t.lat, t.lon
        c.n += 1
        if label is not None:
            self.register_label(t, label, t.ts + self.label_delay_s)

    def process(self, t: Txn, label: int | None = None) -> dict:
        f = self.features(t)
        self.update(t, label)
        return f
