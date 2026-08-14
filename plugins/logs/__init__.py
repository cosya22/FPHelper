"""Просмотр последних строк лога прямо из Telegram."""

import html
import os

from fphelper import PluginInfo

INFO = PluginInfo(
    name="Logs",
    version="1.0.0",
    description="/logs [N] — последние N строк из logs/fphelper.log (по умолчанию 30).",
    author="you",
)

LOG_PATH = os.path.join("logs", "fphelper.log")
MAX_LINES = 100
MAX_MESSAGE_CHARS = 3500


def setup(ctx):
    @ctx.telegram.command("logs")
    def cmd_logs(message):
        parts = message.text.split(maxsplit=1)
        count = 30
        if len(parts) > 1 and parts[1].strip().isdigit():
            count = min(int(parts[1].strip()), MAX_LINES)

        if not os.path.exists(LOG_PATH):
            ctx.telegram.reply(message, "Лог пока пуст.")
            return

        with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-count:]

        text = "".join(lines).strip() or "Лог пуст."
        if len(text) > MAX_MESSAGE_CHARS:
            text = text[-MAX_MESSAGE_CHARS:]
        ctx.telegram.reply(message, f"<pre>{html.escape(text)}</pre>")
