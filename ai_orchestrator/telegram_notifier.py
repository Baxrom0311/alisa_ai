"""Telegram bot notifier for the AI Agent Orchestrator."""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Any, Dict


class TelegramNotifier:
    """Sends status updates to a Telegram chat via Bot API (no dependencies)."""

    def __init__(self, bot_token: str = "", chat_id: str = "", enabled: bool = False):
        self.bot_token = bot_token
        self.chat_id = str(chat_id)
        self.enabled = enabled and bool(bot_token) and bool(chat_id)

    def send(self, text: str, parse_mode: str = "Markdown") -> bool:
        if not self.enabled:
            return False
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = json.dumps({
            "chat_id": self.chat_id,
            "text": text[:4096],
            "parse_mode": parse_mode,
        }).encode()
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception:
            return False

    # ── Notification helpers ───────────────────────────────

    def notify_start(self, project_name: str, plan_cycles: int,
                     review_cycles: int, build_iterations: int) -> None:
        self.send(
            f"🚀 *Orchestrator started*\n"
            f"Project: `{_esc(project_name)}`\n"
            f"Plan: {plan_cycles} | Review: {review_cycles} | Build: {build_iterations}"
        )

    def notify_plan(self, cycle: int, total: int, summary: str) -> None:
        self.send(f"📋 *Plan cycle {cycle}/{total}*\n\n{_esc(summary)}")

    def notify_build_done(self, plan_cycle: int, review_cycle: int, builds: int) -> None:
        self.send(
            f"🔨 Build done — P{plan_cycle} R{review_cycle} ({builds} iterations)"
        )

    def notify_review(self, plan_cycle: int, review_cycle: int,
                      total: int, snippet: str) -> None:
        self.send(
            f"🔍 *Kiro review* P{plan_cycle} R{review_cycle}/{total}\n\n{_esc(snippet)}"
        )

    def notify_replan(self, cycle: int, total: int, summary: str) -> None:
        self.send(f"🧠 *Kiro replan* {cycle}/{total}\n\n{_esc(summary)}")

    def notify_error(self, error: str) -> None:
        self.send(f"❌ *Error*\n\n`{_esc(error[:1500])}`")

    def notify_done(self, summary: Dict[str, Any]) -> None:
        self.send(
            f"🏁 *Orchestrator finished*\n\n"
            f"Done: {summary.get('done')}\n"
            f"Reason: {_esc(str(summary.get('reason', '')))}\n"
            f"Plan cycles: {summary.get('plan_cycles_completed')}\n"
            f"Total builds: {summary.get('total_build_iterations')}"
        )


def _esc(text: str) -> str:
    """Escape Markdown special chars for Telegram."""
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, "\\" + ch)
    return text[:1000]
