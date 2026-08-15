"""
Авто-выдача товара по новому заказу. Два режима на ключевое слово:
- text  — фиксированный текст (для, например, гайда доступа/ссылки)
- stock — список одноразовых позиций (ключи, коды), каждая уходит ровно одному покупателю

Ключевое слово ищется как подстрока в описании заказа (без учёта регистра) —
то есть в названии лота должно встречаться слово, на которое вы настроили выдачу.
"""

from fphelper import PluginInfo, blacklist

INFO = PluginInfo(
    name="Auto Delivery",
    version="1.2.0",
    description="Автоматически выдаёт товар (текст или позицию со склада) сразу после оплаты заказа.",
    author="you",
)


def setup(ctx):
    def get_rules():
        return ctx.storage.get("rules", {})

    def save_rules(rules):
        ctx.storage.set("rules", rules)

    def find_rule(description: str):
        text = description.lower()
        for keyword, rule in get_rules().items():
            if keyword.lower() in text:
                return keyword, rule
        return None, None

    def build_list_text():
        rules = get_rules()
        if not rules:
            return "Правил авто-выдачи пока нет."
        lines = ["<b>Правила авто-выдачи:</b>\n"]
        for keyword, rule in rules.items():
            if rule["type"] == "text":
                lines.append(f"• <b>{keyword}</b> — текст: {rule['content'][:50]}")
            else:
                lines.append(f"• <b>{keyword}</b> — склад: {len(rule.get('items', []))} шт.")
        return "\n".join(lines)

    @ctx.events.new_order
    def on_order(event):
        order = event.order
        keyword, rule = find_rule(order.description)
        if not rule:
            return
        if blacklist.is_restricted(order.buyer_username, "no_delivery"):
            ctx.logger.info(f"Заказ {order.id}: покупатель {order.buyer_username} в чёрном списке, авто-выдача пропущена")
            return

        try:
            chat = ctx.account.get_chat_by_name(order.buyer_username, make_request=True)
            if chat is None:
                raise RuntimeError("не найден чат с покупателем")
            chat_id = chat.id
        except Exception as e:
            ctx.notify_owner(f"❌ Заказ {order.id}: не удалось открыть чат с покупателем — {e}")
            return

        if rule["type"] == "text":
            content = rule["content"]
        else:
            items = rule.get("items", [])
            if not items:
                ctx.notify_owner(
                    f"⚠️ Заказ {order.id}: сработало правило «{keyword}», но склад пуст — выдайте вручную."
                )
                return
            content = items.pop(0)
            rules = get_rules()
            rules[keyword]["items"] = items
            save_rules(rules)

        try:
            ctx.account.send_message(chat_id, content)
        except Exception as e:
            ctx.notify_owner(f"❌ Заказ {order.id}: не удалось отправить выдачу — {e}")
            return

        ctx.notify_owner(
            f"✅ Заказ {order.id}: выдано по правилу «{keyword}» ({order.buyer_username})", event_type="delivery"
        )

    @ctx.telegram.command("delivery_list")
    def cmd_list(message):
        ctx.telegram.reply(message, build_list_text())

    @ctx.telegram.command("delivery_add_text")
    def cmd_add_text(message):
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            ctx.telegram.reply(message, "Использование: /delivery_add_text <ключевое_слово> <текст выдачи>")
            return
        keyword, content = parts[1], parts[2]
        rules = get_rules()
        rules[keyword] = {"type": "text", "content": content}
        save_rules(rules)
        ctx.telegram.reply(message, f"✅ Правило «{keyword}» добавлено (текст).")

    @ctx.telegram.command("delivery_stock_add")
    def cmd_stock_add(message):
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            ctx.telegram.reply(
                message,
                "Использование: /delivery_stock_add <ключевое_слово> <позиция>\n"
                "Вызывайте по разу на каждую позицию (ключ, код и т.п.) — они уходят по одной за заказ.",
            )
            return
        keyword, item = parts[1], parts[2]
        rules = get_rules()
        rule = rules.get(keyword, {"type": "stock", "items": []})
        rule["type"] = "stock"
        rule.setdefault("items", []).append(item)
        rules[keyword] = rule
        save_rules(rules)
        ctx.telegram.reply(message, f"✅ Добавлено на склад «{keyword}» ({len(rule['items'])} шт. в наличии).")

    @ctx.telegram.command("delivery_remove")
    def cmd_remove(message):
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            ctx.telegram.reply(message, "Использование: /delivery_remove <ключевое_слово>")
            return
        keyword = parts[1].strip()
        rules = get_rules()
        if keyword not in rules:
            ctx.telegram.reply(message, "Такого правила нет.")
            return
        del rules[keyword]
        save_rules(rules)
        ctx.telegram.reply(message, f"✅ Правило «{keyword}» удалено.")

    SECTION = "🚀 Авто-выдача"

    @ctx.telegram.menu_item(SECTION, "📋 Список правил", "delivery:list", group="УПРАВЛЕНИЕ")
    def cbq_list(call):
        ctx.telegram.bot.send_message(call.message.chat.id, build_list_text())

    @ctx.telegram.menu_item(SECTION, "➕ Текстовое правило", "delivery:add_text_ask", group="НАСТРОЙКИ")
    def cbq_add_text_ask(call):
        def on_keyword(msg):
            keyword = msg.text.strip()

            def on_text(msg2):
                rules = get_rules()
                rules[keyword] = {"type": "text", "content": msg2.text}
                save_rules(rules)
                ctx.telegram.bot.send_message(msg2.chat.id, f"✅ Правило «{keyword}» добавлено (текст).")

            ctx.telegram.ask(msg.chat.id, msg.from_user.id, "Теперь пришлите текст выдачи.", on_text)

        ctx.telegram.ask(
            call.message.chat.id, call.from_user.id,
            "Пришлите ключевое слово (подстрока в названии лота, на которую сработает выдача).",
            on_keyword,
        )

    @ctx.telegram.menu_item(SECTION, "📦 Добавить на склад", "delivery:stock_add_ask", group="НАСТРОЙКИ")
    def cbq_stock_add_ask(call):
        def on_keyword(msg):
            keyword = msg.text.strip()

            def on_item(msg2):
                rules = get_rules()
                rule = rules.get(keyword, {"type": "stock", "items": []})
                rule["type"] = "stock"
                rule.setdefault("items", []).append(msg2.text)
                rules[keyword] = rule
                save_rules(rules)
                ctx.telegram.bot.send_message(
                    msg2.chat.id, f"✅ Добавлено на склад «{keyword}» ({len(rule['items'])} шт. в наличии)."
                )

            ctx.telegram.ask(msg.chat.id, msg.from_user.id, "Теперь пришлите позицию (код/ключ) для склада.", on_item)

        ctx.telegram.ask(
            call.message.chat.id, call.from_user.id,
            "Пришлите ключевое слово, на которое настроен склад.",
            on_keyword,
        )

    @ctx.telegram.menu_item(SECTION, "🗑 Удалить правило", "delivery:remove_ask", group="НАСТРОЙКИ")
    def cbq_remove_ask(call):
        def on_keyword(msg):
            keyword = msg.text.strip()
            rules = get_rules()
            if keyword not in rules:
                ctx.telegram.bot.send_message(msg.chat.id, "Такого правила нет.")
                return
            del rules[keyword]
            save_rules(rules)
            ctx.telegram.bot.send_message(msg.chat.id, f"✅ Правило «{keyword}» удалено.")

        ctx.telegram.ask(call.message.chat.id, call.from_user.id, "Пришлите ключевое слово правила для удаления.", on_keyword)
