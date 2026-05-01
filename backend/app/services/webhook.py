from __future__ import annotations

import structlog
import httpx

from app.utils.retry import async_retry_on_network_error

log = structlog.get_logger()

_MAX_CONTENT = 1900  # Discord hard limit is 2000; leave headroom for formatting


@async_retry_on_network_error(attempts=3)
async def _post(webhook_url: str, payload: dict) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(webhook_url, json=payload)
        resp.raise_for_status()


async def deliver_to_discord(webhook_url: str, trip_plan: str, user_email: str) -> None:
    """
    Fire-and-forget Discord webhook delivery.

    Always returns without raising — failure is logged but must never surface
    to the caller, since the user has already received their HTTP response.
    """
    content = f"**New Trip Plan for {user_email}**\n\n{trip_plan[:_MAX_CONTENT]}"
    try:
        await _post(webhook_url, {"content": content})
        log.info("webhook.discord_sent", user_email=user_email, chars=len(content))
    except Exception as exc:
        log.error("webhook.discord_failed", user_email=user_email, error=str(exc))
