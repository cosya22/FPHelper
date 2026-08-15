"""
Статистика за период: считает свои новые заказы и сообщения от покупателей,
начиная с момента установки плагина (истории до этого у бота нет — FunPay
её не отдаёт), и показывает разбивку за 24 часа / неделю / месяц / всё время.
"""

import time

from fphelper import PluginInfo

INFO = PluginInfo(
    name="Stats",
    version="1.0.0",
    description="/stats — заказы, выручка и сообщения покупателей за 24ч/неделю/месяц/всё время.",
    author="you",
)

SECTION = "📊 Статистика"

PERIODS = [
    ("24 часа", 24 * 3600),
    ("Неделя", 7 * 24 * 3600),
    ("Месяц", 30 * 24 * 3600),
    ("Всё время", None),
]

MAX_AGE_SECONDS = 400 * 24 * 3600  # чистим записи старше ~400 дней, чтобы файл не рос бесконечно


def setup(ctx):
    def load():
        data = ctx.storage.all()
        data.setdefault("orders", [])   # [[timestamp, price], ...]
        data.setdefault("messages", [])  # [timestamp, ...]
        return data

    def prune_and_save(data):
        cutoff = time.time() - MAX_AGE_SECONDS
        data["orders"] = [o for o in data["orders"] if o[0] >= cutoff]
        data["messages"] = [m for m in data["messages"] if m >= cutoff]
        ctx.storage.update(data)

    @ctx.events.new_order
    def on_order(event):
        data = load()
        data["orders"].append([time.time(), event.order.price or 0])
        prune_and_save(data)

    @ctx.events.new_message
    def on_message(event):
        message = event.message
        # author_id == 0 — системные строки FunPay ("оплатил заказ" и т.п.), не сообщение покупателя.
        if message.author_id in (ctx.account.id, 0):
            return
        data = load()
        data["messages"].append(time.time())
        prune_and_save(data)

    def build_stats_text():
        data = load()
        now = time.time()
        lines = ["<b>📊 Статистика</b>\n"]
        for label, seconds in PERIODS:
            cutoff = now - seconds if seconds else 0
            orders = [o for o in data["orders"] if o[0] >= cutoff]
            messages_count = sum(1 for m in data["messages"] if m >= cutoff)
            revenue = sum(o[1] for o in orders)
            lines.append(
                f"<b>{label}:</b> заказов <code>{len(orders)}</code>, "
                f"выручка <code>{revenue:.0f}</code>, сообщений <code>{messages_count}</code>"
            )
        lines.append("\n<i>Считается с момента установки плагина.</i>")
        return "\n".join(lines)

    @ctx.telegram.command("stats")
    def cmd_stats(message):
        ctx.telegram.reply(message, build_stats_text())

    @ctx.telegram.menu_item(SECTION, "📊 Показать статистику", "stats:show")
    def cbq_show(call):
        ctx.telegram.bot.send_message(call.message.chat.id, build_stats_text())
