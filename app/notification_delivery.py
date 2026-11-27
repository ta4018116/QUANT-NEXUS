"""Optional alert delivery through operator-configured Telegram or HTTPS webhook."""
from __future__ import annotations

import os
import time
from typing import Any

_SENT: dict[str, float] = {}


async def deliver_notification(client, event: dict) -> dict:
    """Deliver one deduplicated event, or report the exact missing transport."""
    dedupe_key = str(event.get("dedupe_key") or "")
    now = time.time()
    for key, expiry in list(_SENT.items()):
        if expiry <= now:
            _SENT.pop(key, None)
    if dedupe_key and dedupe_key in _SENT:
        return {"status": "suppressed_duplicate", "delivery_performed": False}

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    webhook = os.getenv("ALERT_WEBHOOK_URL", "")
    payload = {
        "type": str(event.get("type", "INFO"))[:32],
        "title": str(event.get("title", "QUANT NEXUS"))[:100],
        "message": str(event.get("message", ""))[:1000],
        "dedupe_key": dedupe_key[:180],
    }
    try:
        if token and chat_id:
            response = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": f"{payload['title']}\n{payload['message']}"},
            )
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict) or result.get("ok") is not True:
                return {"status": "delivery_failed", "provider": "Telegram", "delivery_performed": False}
            provider = "Telegram"
        elif webhook:
            response = await client.post(webhook, json=payload, headers={"Content-Type": "application/json"})
            response.raise_for_status()
            provider = "HTTPS webhook"
        else:
            return {
                "status": "transport_not_configured",
                "delivery_performed": False,
                "required": ["TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID or ALERT_WEBHOOK_URL"],
            }
        if dedupe_key:
            _SENT[dedupe_key] = now + max(60, min(86400, int(os.getenv("ALERT_DEDUPE_TTL_SECONDS", "900"))))
        return {"status": "delivered", "provider": provider, "delivery_performed": True}
    except Exception as exc:
        return {"status": "delivery_failed", "provider": "configured_transport", "reason": type(exc).__name__, "delivery_performed": False}
