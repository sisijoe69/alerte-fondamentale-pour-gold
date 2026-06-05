"""TradingView webhook receiver.

Hosts an aiohttp endpoint at `/tv` that accepts JSON alerts from TradingView.
Expected payload :
    {
        "secret":  "<your WEBHOOK_SECRET>",
        "symbol":  "XAUUSD",
        "action":  "BUY" | "SELL" | "ALERT",
        "price":   2400.55,
        "message": "Optional free text"
    }

Forwards a formatted message to every subscriber that hasn't opted out of
alerts, and tags the current fundamental bias from the last stored report.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Awaitable, Callable

from aiohttp import web

from .config import Settings
from .db import Database

logger = logging.getLogger(__name__)

BroadcastFn = Callable[[str], Awaitable[None]]


def _format_payload(payload: dict, last_bias: str | None) -> str:
    symbol = str(payload.get("symbol") or "n/a")
    action = str(payload.get("action") or "ALERT").upper()
    price = payload.get("price")
    message = payload.get("message") or ""

    emoji = {"BUY": "🟢", "SELL": "🔴", "ALERT": "⚠️"}.get(action, "📊")
    lines = [f"{emoji} *TradingView — {action} {symbol}*"]
    if price is not None:
        lines.append(f"💰 Prix : {price}")
    if message:
        lines.append(f"📝 {message}")
    if last_bias:
        lines.append("")
        lines.append(f"🎯 _Biais fondamental actuel : {last_bias}_")
    lines.append("")
    lines.append(f"_TradingView · {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}_")
    return "\n".join(lines)


def build_webhook_app(settings: Settings, db: Database, broadcast: BroadcastFn) -> web.Application:
    app = web.Application()

    async def health(_request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "service": "gold-bot-webhook"})

    async def receive(request: web.Request) -> web.Response:
        try:
            raw = await request.text()
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            logger.warning("TV webhook: invalid JSON")
            return web.json_response({"error": "invalid_json"}, status=400)

        if settings.webhook_secret:
            if payload.get("secret") != settings.webhook_secret:
                logger.warning("TV webhook: bad/missing secret from %s", request.remote)
                return web.json_response({"error": "unauthorized"}, status=401)

        last_bias = None
        try:
            last = db.last_reports(limit=1)
            if last:
                last_bias = f"{last[0].bias} ({last[0].conviction})"
        except Exception:  # noqa: BLE001
            pass

        message = _format_payload(payload, last_bias)
        try:
            await broadcast(message)
            db.log_alert("tradingview", payload)
        except Exception as exc:  # noqa: BLE001
            logger.exception("TV webhook: broadcast failed")
            return web.json_response({"error": "broadcast_failed", "detail": str(exc)}, status=500)

        return web.json_response({"status": "delivered"})

    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    app.router.add_post("/tv", receive)
    app.router.add_post("/tv/", receive)
    return app
