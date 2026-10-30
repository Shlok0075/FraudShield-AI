# Real-Time System Design (Week 11)

## Why WebSockets over polling

Polling wastes requests and adds latency up to the poll interval. WebSockets keep a persistent connection so
the server pushes events the instant they happen — appropriate for a live fraud-monitoring dashboard where
seconds matter (NFR2: dashboard update latency < 2s).

## Events

| Event | Emitted when |
|---|---|
| `new_transaction` | Any transaction is saved (any risk level) |
| `new_alert` | A `fraud_alerts` row is created |
| `alert_updated` | An alert's status changes (multi-admin visibility) |

Implementation: `backend/app/websocket/socket_server.py` (python-socketio, ASGI, mounted at `/socket.io` on the
same FastAPI app — no separate server process). Frontend: `frontend/src/services/socket.js`
(`socket.io-client`), consumed in `Dashboard.jsx` and `Alerts.jsx` via `useEffect` subscriptions — no polling
anywhere in the frontend.

## Verified sequence (this repo, live test)

```
Sim/API -> POST /transactions/predict
API -> ML model (ModelService.predict)
ML  -> probability, risk_score
API -> DB: save transaction + prediction
API -> DB: save alert (if risk >= MEDIUM)
API -> WS: emit new_alert / new_transaction
WS  -> Dashboard client: push event
UI  -> update React state, re-render (no refresh)
```

Confirmed end-to-end against a live Postgres-backed backend and a live Vite dev server
(see `docs/test_report.md` for the exact screenshots/log).

## Reconnection

`socket.io-client`'s default reconnection logic (exponential backoff) requires no extra configuration; verified
by stopping/restarting the backend process during manual QA (Week 11 Day 6).

## Testing without real money

All real-time testing uses `scripts/simulator.py`, which posts fabricated transactions with clearly synthetic
user/device ids and labeled-synthetic amounts/locations. **Never** wired to a real payment processor.

## Sample simulator scenarios (PART 13.4)

| Scenario | Trigger |
|---|---|
| Normal | Known device, modest amount |
| Suspicious | New device + high amount + unusual location |
| High-value | Amount far above typical range |
| Rapid repeated | 3+ transactions within 60 seconds |
| New device | `device_id` never seen for this user |
| Unusual location | Location far from the user's usual pattern |

All six are implemented in `scripts/simulator.py`.
