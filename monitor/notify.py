"""Turn changes into a short report and optionally send it to Telegram."""

from __future__ import annotations

import logging
import os

import requests

from .storage import Changes

log = logging.getLogger(__name__)
MAX_LINES = 10  # per section, keeps the message readable


def build_report(changes: Changes, total: int) -> str:
    lines = [f"Book catalog check: {total} books scanned."]

    def section(title: str, items: list[str]) -> None:
        if not items:
            return
        lines.append("")
        lines.append(f"{title} ({len(items)}):")
        lines.extend(f"- {item}" for item in items[:MAX_LINES])
        if len(items) > MAX_LINES:
            lines.append(f"- ...and {len(items) - MAX_LINES} more")

    section("Price changes", [f"{b.title}: £{old} -> £{b.price}" for b, old in changes.price_changed])
    section("New books", [f"{b.title} (£{b.price})" for b in changes.new])
    section("Back in stock", [b.title for b in changes.back_in_stock])
    section("Removed", changes.removed)

    if not changes.any:
        lines.append("No changes since the last run.")
    return "\n".join(lines)


def send_telegram(text: str) -> bool:
    """Send the report if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set; otherwise just log it."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        log.info("Telegram is not configured, skipping the alert")
        return False

    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        timeout=15,
    )
    if not resp.ok:
        log.error("Telegram returned %s: %s", resp.status_code, resp.text[:200])
        return False
    return True
