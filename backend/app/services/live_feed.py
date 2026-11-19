"""
FraudShield AI - Built-in live transaction feed
==============================================
The dashboard is only interesting while transactions are flowing through the
real scoring pipeline. Previously that required running `scripts/simulator.py`
in a separate terminal before the dashboard showed anything, which meant a fresh
clone opened onto a permanently static page.

This service generates synthetic traffic in-process and pushes it through
`services.prediction_pipeline.ingest_transaction` -- the same function the HTTP
endpoint calls -- so every fed transaction produces real features, a real model
score, a persisted prediction, alerts/cases where warranted, and WebSocket
events. It starts automatically in the app lifespan.

ACADEMIC DISCLAIMER: every user_id, device_id, amount and location generated
here is fabricated. None of it is real payment data.
"""
import asyncio
import logging
import random
from datetime import datetime, timezone

from app.config.settings import settings
from app.database import SessionLocal
from app.services.prediction_pipeline import ingest_transaction

log = logging.getLogger(__name__)

# A small pool of synthetic actors/devices/locations, matching the shape the
# behavioral features expect (repeat users, a few novel devices, a few places
# that imply impossible travel).
KNOWN_USERS = list(range(1, 11))
KNOWN_DEVICES = {u: f"dev-user{u}-primary" for u in KNOWN_USERS}
KNOWN_LOCATIONS = ["Mumbai", "Delhi", "Bengaluru", "Pune", "Chennai", "Hyderabad"]
UNUSUAL_LOCATIONS = ["Lagos", "Minsk", "Unknown-VPN-Exit", "Reykjavik"]

# Traffic mix. Real card/UPI fraud in Asia is a few percent of volume at most, so the feed is
# built from two pools and `LIVE_FEED_FRAUD_RATE` (default 3%) decides how often a transaction is
# an attack. The old single list was ~60% attack-style traffic, which pushed the dashboard's
# fraud rate to 7-8%.
#   LEGIT   - ordinary customers, plus a little unusual-but-genuine behaviour (a big purchase, a
#             new phone, travelling) so the model still has to tell it apart from fraud.
#   ATTACK  - the patterns an analyst actually wants to see.
LEGIT_SCENARIOS = [
    ("normal", 88),
    ("high_value", 4),
    ("new_device", 4),
    ("rapid_repeated", 2),
    ("unusual_location", 2),
]
ATTACK_SCENARIOS = [
    ("account_takeover", 30),
    ("card_testing", 25),
    ("suspicious", 15),
    ("transaction_splitting", 15),
    ("fraud_ring", 15),
]
SCENARIOS = LEGIT_SCENARIOS + ATTACK_SCENARIOS   # every scenario the feed can produce


def _expand(table: list[tuple[str, int]]) -> list[str]:
    out: list[str] = []
    for name, weight in table:
        out.extend([name] * weight)
    return out


def _weighted_scenarios() -> list[str]:
    return _expand(SCENARIOS)


def pick_scenario(fraud_rate: float | None = None, rng=random) -> str:
    """One scenario: an attack with probability `fraud_rate`, otherwise legitimate traffic."""
    rate = settings.LIVE_FEED_FRAUD_RATE if fraud_rate is None else fraud_rate
    rate = min(1.0, max(0.0, float(rate)))
    table = ATTACK_SCENARIOS if rng.random() < rate else LEGIT_SCENARIOS
    return rng.choice(_expand(table))


def build_payload(scenario: str) -> dict:
    """Build one synthetic transaction for the given scenario."""
    user_id = random.choice(KNOWN_USERS)

    if scenario == "normal":
        return {
            "user_id": user_id, "amount": round(random.uniform(50, 2000), 2),
            "device_id": KNOWN_DEVICES[user_id],
            "location": random.choice(KNOWN_LOCATIONS), "payment_method": "card",
        }
    if scenario == "suspicious":
        return {
            "user_id": user_id, "amount": round(random.uniform(5000, 20000), 2),
            "device_id": f"dev-suspicious-{random.randint(1000, 9999)}",
            "location": random.choice(KNOWN_LOCATIONS), "payment_method": "card",
        }
    if scenario == "high_value":
        return {
            "user_id": user_id, "amount": round(random.uniform(50000, 400000), 2),
            "device_id": KNOWN_DEVICES[user_id],
            "location": random.choice(KNOWN_LOCATIONS), "payment_method": "card",
        }
    if scenario == "rapid_repeated":
        return {
            "user_id": user_id, "amount": round(random.uniform(100, 900), 2),
            "device_id": KNOWN_DEVICES[user_id],
            "location": random.choice(KNOWN_LOCATIONS), "payment_method": "card",
        }
    if scenario == "new_device":
        return {
            "user_id": user_id, "amount": round(random.uniform(1000, 15000), 2),
            "device_id": f"dev-new-{random.randint(10000, 99999)}",
            "location": random.choice(KNOWN_LOCATIONS), "payment_method": "card",
        }
    if scenario == "unusual_location":
        return {
            "user_id": user_id, "amount": round(random.uniform(2000, 40000), 2),
            "device_id": KNOWN_DEVICES[user_id],
            "location": random.choice(UNUSUAL_LOCATIONS), "payment_method": "card",
        }
    if scenario == "card_testing":
        return {
            "user_id": user_id, "amount": round(random.uniform(1, 25), 2),
            "device_id": KNOWN_DEVICES[user_id],
            "location": random.choice(KNOWN_LOCATIONS), "payment_method": "card",
        }
    if scenario == "account_takeover":
        return {
            "user_id": user_id, "amount": round(random.uniform(20000, 120000), 2),
            "device_id": f"dev-takeover-{random.randint(1000, 99999)}",
            "location": random.choice(UNUSUAL_LOCATIONS), "payment_method": "card",
        }
    if scenario == "transaction_splitting":
        return {
            "user_id": user_id, "amount": round(random.uniform(900, 2500), 2),
            "device_id": KNOWN_DEVICES[user_id],
            "location": random.choice(KNOWN_LOCATIONS), "payment_method": "card",
        }
    # fraud_ring: burst of small transfers to an unusual location.
    return {
        "user_id": user_id, "amount": round(random.uniform(400, 1500), 2),
        "device_id": f"dev-ring-{random.randint(1000, 9999)}",
        "location": random.choice(UNUSUAL_LOCATIONS), "payment_method": "transfer",
    }


class LiveFeed:
    """Background task producing synthetic traffic through the real pipeline."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()
        self.started_at: datetime | None = None
        self.generated = 0
        self.errors = 0
        self.last_error: str | None = None
        self.running = False

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stopping = asyncio.Event()
        self.started_at = datetime.now(timezone.utc)
        self._task = asyncio.create_task(self._run(), name="fraudshield-live-feed")
        self.running = True
        log.info("live feed started (interval=%ss)", settings.LIVE_FEED_INTERVAL_SECONDS)

    async def stop(self) -> None:
        self.running = False
        self._stopping.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None
        log.info("live feed stopped after %d transactions", self.generated)

    # -- status for the dashboard -----------------------------------------
    def status(self) -> dict:
        return {
            "running": self.running and self._task is not None and not self._task.done(),
            "enabled": settings.LIVE_FEED_ENABLED,
            "interval_seconds": settings.LIVE_FEED_INTERVAL_SECONDS,
            "burst_size": settings.LIVE_FEED_BURST,
            "fraud_rate": settings.LIVE_FEED_FRAUD_RATE,
            "generated": self.generated,
            "errors": self.errors,
            "last_error": self.last_error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "scenarios": [name for name, _ in SCENARIOS],
        }

    # -- the loop ----------------------------------------------------------
    async def _run(self) -> None:
        interval = max(0.2, float(settings.LIVE_FEED_INTERVAL_SECONDS))
        burst = max(1, int(settings.LIVE_FEED_BURST))
        log.info("live feed running: %d txn every %.1fs", burst, interval)

        while not self._stopping.is_set():
            for _ in range(burst):
                if self._stopping.is_set():
                    return
                try:
                    await self._emit_one(pick_scenario())
                except Exception as exc:  # noqa: BLE001
                    # A single bad payload must never kill the feed; count it and
                    # keep going, otherwise one transient DB error would silently
                    # freeze the dashboard for the rest of the session.
                    self.errors += 1
                    self.last_error = f"{type(exc).__name__}: {exc}"
                    log.warning("live feed transaction failed: %s", exc)
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    async def _emit_one(self, scenario: str) -> dict:
        payload = build_payload(scenario)
        # The feed is a background writer, so it gets its own short-lived
        # session rather than borrowing a request-scoped one.
        db = SessionLocal()
        try:
            result = await ingest_transaction(db, payload)
            self.generated += 1
            return result
        finally:
            db.close()


# Process-wide singleton the lifespan hooks and the /live-feed route share.
live_feed = LiveFeed()
