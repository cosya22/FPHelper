"""
Автоответы: приветственное сообщение первому написавшему покупателю и авто-ответ
на подтверждение (оплату) заказа. Настройка авто-ответа на отзывы живёт в этом же
разделе меню, но реализована в модуле Reviews (см. builtin/reviews) — там она
привязана к проверке отзывов по закрытым заказам.
"""

from fphelper import PluginInfo, blacklist

INFO = PluginInfo(
    name="Auto Reply",
    version="1.0.0",
    description="Приветственное сообщение новому покупателю и авто-ответ на подтверждение заказа.",
    author="you",
)

SECTION = "🤖 Автоответ"

DEFAULT_TEXTS = {
    "welcome": "Здравствуйте, {username}! Спасибо, что написали 🙂 Если появятся вопросы — обязательно "
               "пишите, отвечу как можно скорее.",
    "order_confirm": "Спасибо за заказ, {username}! Уже занимаюсь им — если нужно будет что-то уточнить, "
                      "напишу прямо сюда.",
}
RULE_LABELS = {
    "welcome": "👋 Приветственное сообщение",
    "order_confirm": "✅ Ответ на подтверждение заказа",
}


def setup(ctx):
    def get_settings():
        settings = ctx.storage.get("settings", {})
        for key, text in DEFAULT_TEXTS.items():
            settings.setdefault(key, {"enabled": False, "text": text})
        return settings

    def save_settings(settings):
        ctx.storage.set("settings", settings)

    def get_greeted():
        return set(ctx.storage.get("greeted_chat_ids", []))

    def save_greeted(greeted):
        ctx.storage.set("greeted_chat_ids", list(greeted))

    @ctx.events.new_message
    def on_first_message(event):
        message = event.message
        if message.author_id == ctx.account.id or not message.text:
            return
        rule = get_settings()["welcome"]
        if not rule["enabled"] or not rule["text"]:
            return
        if blacklist.is_blacklisted(message.author):
            return
        greeted = get_greeted()
        if message.chat_id in greeted:
            return
        greeted.add(message.chat_id)
        save_greeted(greeted)
        try:
            ctx.account.send_message(message.chat_id, rule["text"].format(username=message.author or ""))
        except Exception:
            ctx.logger.exception("Не удалось отправить приветственное сообщение")

    @ctx.events.new_order
    def on_order(event):
        order = event.order
        rule = get_settings()["order_confirm"]
        if not rule["enabled"] or not rule["text"]:
            return
        if blacklist.is_blacklisted(order.buyer_username):
            return
        try:
            chat = ctx.account.get_chat_by_name(order.buyer_username, make_request=True)
            if chat is None:
                raise RuntimeError("не найден чат с покупателем")
            ctx.account.send_message(chat.id, rule["text"].format(username=order.buyer_username))
        except Exception as e:
            ctx.notify_owner(f"⚠️ Заказ {order.id}: не удалось отправить авто-ответ на подтверждение — {e}")

    for key in ("welcome", "order_confirm"):
        def make_toggle(key=key):
            def toggle_label():
                rule = get_settings()[key]
                return f"{'🟢' if rule['enabled'] else '🔴'} {RULE_LABELS[key]}"
            return toggle_label

        def make_toggle_handler(key=key):
            def cbq_toggle(call):
                settings = get_settings()
                settings[key]["enabled"] = not settings[key]["enabled"]
                save_settings(settings)
                ctx.telegram.refresh_section(call, SECTION)
            return cbq_toggle

        def make_text_handler(key=key):
            def cbq_text_ask(call):
                def on_text(msg):
                    settings = get_settings()
                    settings[key]["text"] = msg.text
                    save_settings(settings)
                    ctx.telegram.bot.send_message(msg.chat.id, f"✅ Текст «{RULE_LABELS[key]}» сохранён.")

                ctx.telegram.ask(
                    call.message.chat.id, call.from_user.id,
                    f"Новый текст «{RULE_LABELS[key]}» (можно использовать {{username}})?",
                    on_text,
                )
            return cbq_text_ask

        ctx.telegram.menu_item(SECTION, make_toggle(), f"autoreply:toggle:{key}", group=RULE_LABELS[key])(
            make_toggle_handler()
        )
        ctx.telegram.menu_item(SECTION, "✏️ Изменить текст", f"autoreply:text_ask:{key}", group=RULE_LABELS[key])(
            make_text_handler()
        )
