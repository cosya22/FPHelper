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
    version="1.4.0",
    description="Уведомляет о новых отзывах, умеет отвечать автоматически по количеству звёзд "
                 "(настройка авто-ответа — в разделе «🤖 Автоответ», вместе с остальными автоответами).",
    author="you",
)

CHECK_INTERVAL = 600
MAX_ORDERS_PER_CHECK = 30

# Тексты авто-ответа по умолчанию (можно использовать {username}) — сами по себе
# не включены (enabled: False), просто чтобы не начинать с пустого поля.
DEFAULT_REVIEW_TEXTS = {
    "5": "Спасибо большое за такую высокую оценку, {username}! Обращайтесь ещё 😊",
    "4": "Спасибо за отзыв, {username}! Будем рады видеть вас снова.",
    "3": "Спасибо за отзыв, {username}. Обязательно учтём ваши пожелания.",
    "2": "Жаль, что не всё понравилось, {username}. Напишите, пожалуйста, в чат, что не так — постараемся исправить.",
    "1": "Очень жаль это слышать, {username}. Пожалуйста, напишите нам в чат — разберёмся и всё исправим.",
}


def setup(ctx):
    def get_seen():
        return set(ctx.storage.get("seen_order_ids", []))

    def save_seen(seen):
        ctx.storage.set("seen_order_ids", list(seen))

    def get_auto_reply():
        settings = ctx.storage.get("auto_reply", {})
        for stars in range(1, 6):
            settings.setdefault(str(stars), {"enabled": False, "text": DEFAULT_REVIEW_TEXTS[str(stars)]})
        return settings

    def save_auto_reply(settings):
        ctx.storage.set("auto_reply", settings)

    def worker():
        while True:
            time.sleep(CHECK_INTERVAL)
            try:
                _, closed_orders = ctx.account.get_sells(state="closed")
            except Exception:
                ctx.logger.exception("Не удалось получить закрытые заказы")
                continue

            # первый запуск (хранилище ещё пустое) — только запоминаем уже существующие
            # отзывы как увиденные, не уведомляя о них как о новых
            first_run = ctx.storage.get("seen_order_ids", None) is None
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
                if not first_run:
                    ctx.notify_owner(
                        f"🌟 Новый отзыв ({order.review.stars}/5) по заказу {order.id}\n"
                        f"От {order.buyer_username}: {order.review.text}\n\n"
                        f"Ответить: /review_reply {order.id} текст",
                        event_type="review",
                    )

                    rule = get_auto_reply().get(str(order.review.stars))
                    if rule and rule["enabled"] and rule["text"]:
                        try:
                            ctx.account.send_review(order.id, rule["text"].format(username=order.buyer_username))
                            ctx.notify_owner(
                                f"🤖 Авто-ответ на отзыв ({order.review.stars}/5) по заказу {order.id} отправлен",
                                event_type="review",
                            )
                        except Exception as e:
                            ctx.notify_owner(
                                f"⚠️ Не удалось авто-ответить на отзыв по заказу {order.id}: {e}",
                                event_type="review",
                            )

            if changed or first_run:
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
    # Настройка авто-ответа по звёздам — не сюда, а в общий раздел "Автоответ"
    # вместе с приветствием и ответом на подтверждение заказа, чтобы в "Отзывах"
    # были только сами отзывы.
    AUTOREPLY_SECTION = "🤖 Автоответ"

    @ctx.telegram.menu_item(SECTION, "✍️ Ответить на отзыв", "reviews:reply_ask", group="УПРАВЛЕНИЕ")
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

    @ctx.telegram.menu_item(SECTION, "🗑 Удалить ответ", "reviews:delete_ask", group="УПРАВЛЕНИЕ")
    def cbq_delete_ask(call):
        def on_id(msg):
            order_id = msg.text.strip()
            try:
                ctx.account.delete_review(order_id)
                ctx.telegram.bot.send_message(msg.chat.id, "✅ Ответ на отзыв удалён.")
            except Exception as e:
                ctx.telegram.bot.send_message(msg.chat.id, f"❌ Не удалось удалить ответ: {e}")

        ctx.telegram.ask(call.message.chat.id, call.from_user.id, "Пришлите ID заказа.", on_id)

    for stars in range(1, 6):
        def make_toggle(stars=stars):
            def toggle_label():
                rule = get_auto_reply()[str(stars)]
                return f"{'🟢' if rule['enabled'] else '🔴'} Авто-ответ {'⭐' * stars}"
            return toggle_label

        def make_handler(stars=stars):
            def cbq_toggle(call):
                settings = get_auto_reply()
                rule = settings[str(stars)]
                if not rule["enabled"] and not rule["text"]:
                    def on_text(msg):
                        s = get_auto_reply()
                        s[str(stars)] = {"enabled": True, "text": msg.text}
                        save_auto_reply(s)
                        ctx.telegram.bot.send_message(msg.chat.id, f"✅ Авто-ответ на {stars}⭐ включён.")

                    ctx.telegram.ask(
                        call.message.chat.id, call.from_user.id,
                        f"Текст авто-ответа на отзыв {stars}⭐ (можно использовать {{username}})?",
                        on_text,
                    )
                    return
                rule["enabled"] = not rule["enabled"]
                save_auto_reply(settings)
                ctx.telegram.refresh_section(call, AUTOREPLY_SECTION)
            return cbq_toggle

        ctx.telegram.menu_item(
            AUTOREPLY_SECTION, make_toggle(), f"reviews:autoreply_toggle:{stars}", group="🌟 Авто-ответ на отзывы"
        )(make_handler())

    @ctx.telegram.menu_item(
        AUTOREPLY_SECTION, "✏️ Изменить текст авто-ответа на отзыв", "reviews:autoreply_text_ask",
        group="🌟 Авто-ответ на отзывы",
    )
    def cbq_autoreply_text_ask(call):
        def on_stars(msg):
            if msg.text.strip() not in ("1", "2", "3", "4", "5"):
                ctx.telegram.bot.send_message(msg.chat.id, "Нужно число от 1 до 5.")
                return
            stars = msg.text.strip()

            def on_text(msg2):
                settings = get_auto_reply()
                settings[stars]["text"] = msg2.text
                save_auto_reply(settings)
                ctx.telegram.bot.send_message(msg2.chat.id, f"✅ Текст авто-ответа на {stars}⭐ сохранён.")

            ctx.telegram.ask(
                msg.chat.id, msg.from_user.id, f"Новый текст авто-ответа на {stars}⭐ (можно {{username}})?", on_text
            )

        ctx.telegram.ask(call.message.chat.id, call.from_user.id, "На сколько звёзд меняем текст (1-5)?", on_stars)
