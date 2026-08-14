"""Просмотр и управление заказами: список, детали, возврат."""

from fphelper import PluginInfo
from FunPayAPI.common.enums import OrderStatuses

INFO = PluginInfo(
    name="Orders",
    version="1.0.0",
    description="/orders — список заказов, /order <id> — детали, /refund <id> — возврат.",
    author="you",
)

MAX_ORDERS_SHOWN = 15

STATUS_ICONS = {
    OrderStatuses.PAID: "🟢",
    OrderStatuses.CLOSED: "✅",
    OrderStatuses.REFUNDED: "↩️",
}


def setup(ctx):
    @ctx.telegram.command("orders")
    def cmd_orders(message):
        try:
            _, sells = ctx.account.get_sells()
        except Exception as e:
            ctx.telegram.reply(message, f"❌ Не удалось получить заказы: {e}")
            return
        if not sells:
            ctx.telegram.reply(message, "Заказов пока нет.")
            return
        lines = ["<b>Последние заказы:</b>\n"]
        for order in sells[:MAX_ORDERS_SHOWN]:
            icon = STATUS_ICONS.get(order.status, "❔")
            lines.append(
                f"{icon} <code>{order.id}</code> {order.description[:40]} — "
                f"{order.price} — {order.buyer_username}"
            )
        lines.append("\nДетали: <code>/order id</code> · Возврат: <code>/refund id</code>")
        ctx.telegram.reply(message, "\n".join(lines))

    @ctx.telegram.command("order")
    def cmd_order(message):
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            ctx.telegram.reply(message, "Использование: /order <id>")
            return
        try:
            order = ctx.account.get_order(parts[1].strip())
        except Exception as e:
            ctx.telegram.reply(message, f"❌ Не удалось получить заказ: {e}")
            return
        review = ""
        if order.review and order.review.text:
            review = f"\n\n🌟 Отзыв ({order.review.stars}): {order.review.text}"
        text = (
            f"<b>Заказ {order.id}</b>\n\n"
            f"Статус: {order.status.name}\n"
            f"Товар: {order.short_description or order.subcategory.name}\n"
            f"Сумма: {order.sum}\n"
            f"Покупатель: {order.buyer_username}"
            f"{review}"
        )
        ctx.telegram.reply(message, text)

    @ctx.telegram.command("refund")
    def cmd_refund(message):
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            ctx.telegram.reply(message, "Использование: /refund <id>")
            return
        order_id = parts[1].strip()
        try:
            ctx.account.refund(order_id)
        except Exception as e:
            ctx.telegram.reply(message, f"❌ Не удалось оформить возврат: {e}")
            return
        ctx.telegram.reply(message, f"✅ Возврат по заказу {order_id} оформлен.")
