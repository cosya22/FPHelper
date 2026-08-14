"""
Уведомления о новых отзывах + ответ/удаление ответа.

Важное ограничение: в официальной FunPayAPI нет отдельного события "новый отзыв" —
отзыв прикрепляется к уже закрытому заказу без смены его статуса. Поэтому плагин
периодически (раз в CHECK_INTERVAL) опрашивает последнюю страницу закрытых заказов
и проверяет, не появился ли у них отзыв. Это не мгновенно и не проверяет очень
старые заказы — только последнюю пачку закрытых.
"""

import threading
import time

from fphelper import PluginInfo

INFO = PluginInfo(
    name="Reviews",
    version="1.0.0",
    description="Уведомляет о новых отзывах на последние закрытые заказы, позволяет ответить/удалить ответ.",
    author="you",
)

CHECK_INTERVAL = 600
MAX_ORDERS_PER_CHECK = 30


def setup(ctx):
    def get_seen():
        return set(ctx.storage.get("seen_order_ids", []))

    def save_seen(seen):
        ctx.storage.set("seen_order_ids", list(seen))

    def worker():
        while True:
            time.sleep(CHECK_INTERVAL)
            try:
                _, closed_orders = ctx.account.get_sells(state="closed")
            except Exception:
                ctx.logger.exception("Не удалось получить закрытые заказы")
                continue

            seen = get_seen()
            changed = False
            for order_shortcut in closed_orders[:MAX_ORDERS_PER_CHECK]:
                if order_shortcut.id in seen:
                    continue
                try:
                    order = ctx.account.get_order(order_shortcut.id)
                except Exception:
                    continue
                if not order.review or not order.review.text:
                    continue

                seen.add(order.id)
                changed = True
                ctx.notify_admins(
                    f"🌟 Новый отзыв ({order.review.stars}/5) по заказу {order.id}\n"
                    f"От {order.buyer_username}: {order.review.text}\n\n"
                    f"Ответить: /review_reply {order.id} текст"
                )

            if changed:
                save_seen(seen)

    threading.Thread(target=worker, daemon=True).start()

    @ctx.telegram.command("review_reply")
    def cmd_reply(message):
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            ctx.telegram.reply(message, "Использование: /review_reply <order_id> <текст>")
            return
        order_id, text = parts[1], parts[2]
        try:
            ctx.account.send_review(order_id, text)
        except Exception as e:
            ctx.telegram.reply(message, f"❌ Не удалось ответить на отзыв: {e}")
            return
        ctx.telegram.reply(message, "✅ Ответ на отзыв отправлен.")

    @ctx.telegram.command("review_delete")
    def cmd_delete(message):
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            ctx.telegram.reply(message, "Использование: /review_delete <order_id>")
            return
        order_id = parts[1].strip()
        try:
            ctx.account.delete_review(order_id)
        except Exception as e:
            ctx.telegram.reply(message, f"❌ Не удалось удалить ответ: {e}")
            return
        ctx.telegram.reply(message, "✅ Ответ на отзыв удалён.")

    SECTION = "🌟 Отзывы"

    @ctx.telegram.menu_item(SECTION, "✍️ Ответить на отзыв", "reviews:reply_ask")
    def cbq_reply_ask(call):
        def on_id(msg):
            order_id = msg.text.strip()

            def on_text(msg2):
                try:
                    ctx.account.send_review(order_id, msg2.text)
                    ctx.telegram.bot.send_message(msg2.chat.id, "✅ Ответ на отзыв отправлен.")
                except Exception as e:
                    ctx.telegram.bot.send_message(msg2.chat.id, f"❌ Не удалось ответить на отзыв: {e}")

            ctx.telegram.ask(msg.chat.id, msg.from_user.id, "Теперь пришлите текст ответа.", on_text)

        ctx.telegram.ask(call.message.chat.id, call.from_user.id, "Пришлите ID заказа с отзывом.", on_id)

    @ctx.telegram.menu_item(SECTION, "🗑 Удалить ответ", "reviews:delete_ask")
    def cbq_delete_ask(call):
        def on_id(msg):
            order_id = msg.text.strip()
            try:
                ctx.account.delete_review(order_id)
                ctx.telegram.bot.send_message(msg.chat.id, "✅ Ответ на отзыв удалён.")
            except Exception as e:
                ctx.telegram.bot.send_message(msg.chat.id, f"❌ Не удалось удалить ответ: {e}")

        ctx.telegram.ask(call.message.chat.id, call.from_user.id, "Пришлите ID заказа.", on_id)
