"""Просмотр и управление заказами: список, детали, возврат."""

from fphelper import PluginInfo
from FunPayAPI.common.enums import OrderStatuses

INFO = PluginInfo(
    name="Orders",
    version="1.0.0",
    description="/orders — список заказов, /order [id] — детали, /refund [id] — возврат.",
    author="you",
)

SECTION = "📋 Заказы"
MAX_ORDERS_SHOWN = 15

STATUS_ICONS = {
    OrderStatuses.PAID: "🟢",
    OrderStatuses.CLOSED: "✅",
    OrderStatuses.REFUNDED: "↩️",
}


def setup(ctx):
    def build_orders_text():
        _, sells = ctx.account.get_sells()
        if not sells:
            return "Заказов пока нет."
        lines = ["<b>Последние заказы:</b>\n"]
        for order in sells[:MAX_ORDERS_SHOWN]:
            icon = STATUS_ICONS.get(order.status, "❔")
            lines.append(
                f"{icon} <code>{order.id}</code> {order.description[:40]} — "
                f"{order.price} — {order.buyer_username}"
            )
        return "\n".join(lines)

    def build_order_text(order_id):
        order = ctx.account.get_order(order_id)
        review = ""
        if order.review and order.review.text:
            review = f"\n\n🌟 Отзыв ({order.review.stars}): {order.review.text}"
        return (
            f"<b>Заказ {order.id}</b>\n\n"
            f"Статус: {order.status.name}\n"
            f"Товар: {order.short_description or order.subcategory.name}\n"
            f"Сумма: {order.sum}\n"
            f"Покупатель: {order.buyer_username}"
            f"{review}"
        )

    @ctx.telegram.command("orders")
    def cmd_orders(message):
        try:
            text = build_orders_text() + "\n\nДетали: <code>/order id</code> · Возврат: <code>/refund id</code>"
        except Exception as e:
            ctx.telegram.reply(message, f"❌ Не удалось получить заказы: {e}")
            return
        ctx.telegram.reply(message, text)

    @ctx.telegram.command("order")
    def cmd_order(message):
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            ctx.telegram.reply(message, "Использование: /order <id>")
            return
        try:
            text = build_order_text(parts[1].strip())
        except Exception as e:
            ctx.telegram.reply(message, f"❌ Не удалось получить заказ: {e}")
            return
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

    @ctx.telegram.menu_item(SECTION, "📋 Список заказов", "orders:list")
    def cbq_list(call):
        try:
            text = build_orders_text()
        except Exception as e:
            text = f"❌ Не удалось получить заказы: {e}"
        ctx.telegram.bot.send_message(call.message.chat.id, text)

    @ctx.telegram.menu_item(SECTION, "🔍 Заказ по ID", "orders:details_ask")
    def cbq_details_ask(call):
        def on_id(msg):
            try:
                text = build_order_text(msg.text.strip())
            except Exception as e:
                text = f"❌ Не удалось получить заказ: {e}"
            ctx.telegram.bot.send_message(msg.chat.id, text)

        ctx.telegram.ask(call.message.chat.id, call.from_user.id, "Пришлите ID заказа.", on_id)

    @ctx.telegram.menu_item(SECTION, "↩️ Возврат по ID", "orders:refund_ask")
    def cbq_refund_ask(call):
        def on_id(msg):
            order_id = msg.text.strip()
            try:
                ctx.account.refund(order_id)
                ctx.telegram.bot.send_message(msg.chat.id, f"✅ Возврат по заказу {order_id} оформлен.")
            except Exception as e:
                ctx.telegram.bot.send_message(msg.chat.id, f"❌ Не удалось оформить возврат: {e}")

        ctx.telegram.ask(call.message.chat.id, call.from_user.id, "Пришлите ID заказа для возврата.", on_id)
