"""Telegram bot notifier for the AI Agent Orchestrator."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
import urllib.error
from typing import Any, Dict


# ANSI escape code pattern
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]|\x1b\].*?\x07")
# Common kiro-cli noise patterns to strip
_NOISE_RE = re.compile(
    r"(Reading (file|directory):.*?\n|"
    r"↱ Operation \d+:.*?\n|"
    r"\s*✓\s*Successfully (read|wrote).*?\n|"
    r"\s*⋮\s*\n|"
    r"- (Completed in|Summary:).*?\n|"
    r"Batch fs_read operation.*?\n|"
    r"\(using tool:.*?\)\s*)",
    re.MULTILINE,
)


def clean_output(text: str) -> str:
    """Strip ANSI codes and kiro-cli noise from output."""
    text = _ANSI_RE.sub("", text)
    text = _NOISE_RE.sub("", text)
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class TelegramNotifier:
    """Sends status updates to a Telegram chat via Bot API (no dependencies)."""

    def __init__(self, bot_token: str = "", chat_id: str = "", enabled: bool = False):
        # Environment variables take precedence over passed parameters
        self.bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "") or bot_token
        self.chat_id = str(os.environ.get("TELEGRAM_CHAT_ID", "") or chat_id)
        self.enabled = enabled and bool(self.bot_token) and bool(self.chat_id)

    def send(self, text: str, parse_mode: str = "Markdown") -> bool:
        if not self.enabled:
            return False
        text = clean_output(text)
        if not text:
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
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return resp.status == 200
            except Exception:
                if attempt < 2:
                    time.sleep(2)
        return False

    # ── Notification helpers ───────────────────────────────

    def notify_start(self, project_name: str, plan_cycles: int,
                     review_cycles: int, build_iterations: int) -> None:
        self.send(
            f"🚀 *Orchestrator ishga tushdi*\n"
            f"Loyha: `{project_name}`\n"
            f"Rejalar: {plan_cycles} | Reviewlar: {review_cycles} | Buildlar: {build_iterations}"
        )

    def notify_plan(self, cycle: int, total: int, summary: str) -> None:
        short = _extract_summary(summary, max_lines=8)
        self.send(f"📋 *Reja {cycle}/{total}*\n\n{_esc(short)}")

    def notify_build_done(self, plan_cycle: int, review_cycle: int, builds: int) -> None:
        self.send(
            f"🔨 *Build tugadi* — Reja {plan_cycle}, Review {review_cycle} ({builds} iteratsiya)"
        )

    def notify_review(self, plan_cycle: int, review_cycle: int,
                      total: int, snippet: str) -> None:
        short = _extract_summary(snippet, max_lines=6)
        self.send(
            f"🔍 *Review* P{plan_cycle} R{review_cycle}/{total}\n\n{_esc(short)}"
        )

    def notify_replan(self, cycle: int, total: int, summary: str) -> None:
        short = _extract_summary(summary, max_lines=6)
        self.send(f"🧠 *Qayta reja* {cycle}/{total}\n\n{_esc(short)}")

    def notify_error(self, error: str) -> None:
        self.send(f"❌ *Xato*\n\n`{_esc(error[:500])}`")

    def notify_done(self, summary: Dict[str, Any]) -> None:
        self.send(
            f"🏁 *Orchestrator tugadi*\n\n"
            f"Holat: {summary.get('done')}\n"
            f"Sabab: {_esc(str(summary.get('reason', '')))}\n"
            f"Rejalar: {summary.get('plan_cycles_completed')}\n"
            f"Buildlar: {summary.get('total_build_iterations')}"
        )


def _extract_summary(text: str, max_lines: int = 8) -> str:
    """Extract meaningful lines from output, skip noise."""
    text = clean_output(text)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    # Keep only meaningful lines (skip very short or path-only lines)
    meaningful = []
    for line in lines:
        if len(line) < 3:
            continue
        if line.startswith("/Users/") or line.startswith("↱"):
            continue
        meaningful.append(line)
        if len(meaningful) >= max_lines:
            break
    return "\n".join(meaningful) if meaningful else text[:300]


def _esc(text: str) -> str:
    """Escape Markdown special chars for Telegram."""
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, "\\" + ch)
    return text[:1000]
