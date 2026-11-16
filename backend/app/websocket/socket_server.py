"""
FraudShield AI - Real-time WebSocket server (PART 13 / Week 11 Day 1)
==========================================================================
python-socketio mounted onto the FastAPI ASGI app. Events:
  new_transaction : emitted after every transaction is saved (any risk level)
  new_alert       : emitted after a fraud_alerts row is created
  alert_updated   : emitted after an alert's status changes
"""
import socketio

from app.config.settings import settings

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=settings.cors_origins_list,
)
socket_app = socketio.ASGIApp(sio)


async def emit_new_transaction(payload: dict) -> None:
    await sio.emit("new_transaction", payload)


async def emit_new_alert(payload: dict) -> None:
    await sio.emit("new_alert", payload)


async def emit_alert_updated(payload: dict) -> None:
    await sio.emit("alert_updated", payload)


async def emit_investigation_complete(payload: dict) -> None:
    await sio.emit("investigation_complete", payload)


@sio.event
async def connect(sid, environ):
    print(f"[socket.io] client connected: {sid}")


@sio.event
async def disconnect(sid):
    print(f"[socket.io] client disconnected: {sid}")
