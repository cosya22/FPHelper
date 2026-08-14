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
    def build_logs_text(count: int) -> str:
        if not os.path.exists(LOG_PATH):
            return "Лог пока пуст."
        with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-count:]
        text = "".join(lines).strip() or "Лог пуст."
        if len(text) > MAX_MESSAGE_CHARS:
            text = text[-MAX_MESSAGE_CHARS:]
        return f"<pre>{html.escape(text)}</pre>"

    @ctx.telegram.command("logs")
    def cmd_logs(message):
        parts = message.text.split(maxsplit=1)
        count = 30
        if len(parts) > 1 and parts[1].strip().isdigit():
            count = min(int(parts[1].strip()), MAX_LINES)
        ctx.telegram.reply(message, build_logs_text(count))

    @ctx.telegram.menu_item("🗒️ Логи", "🗒️ Последние 30 строк", "logs:show")
    def cbq_show(call):
        ctx.telegram.bot.send_message(call.message.chat.id, build_logs_text(30))
