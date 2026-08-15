"""Быстрые ответы: сохранённые шаблоны текста, которые можно отправить в любой чат одной командой."""

from fphelper import PluginInfo

INFO = PluginInfo(
    name="Fast Replies",
    version="1.1.0",
    description="/freply_add, /freply_list, /freply [имя] [chat_id] — быстрая отправка шаблонов.",
    author="you",
)


def setup(ctx):
    def get_replies():
        return ctx.storage.get("replies", {})

    def save_replies(replies):
        ctx.storage.set("replies", replies)

    def build_list_text():
        replies = get_replies()
        if not replies:
            return "Быстрых ответов пока нет."
        lines = ["<b>Быстрые ответы:</b>\n"]
        for name, text in replies.items():
            lines.append(f"• <b>{name}</b> — {text[:50]}")
        return "\n".join(lines)

    @ctx.telegram.command("freply_add")
    def cmd_add(message):
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            ctx.telegram.reply(message, "Использование: /freply_add [имя] [текст]")
            return
        name, text = parts[1], parts[2]
        replies = get_replies()
        replies[name] = text
        save_replies(replies)
        ctx.telegram.reply(message, f"✅ Быстрый ответ «{name}» сохранён.")

    @ctx.telegram.command("freply_remove")
    def cmd_remove(message):
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            ctx.telegram.reply(message, "Использование: /freply_remove [имя]")
            return
        name = parts[1].strip()
        replies = get_replies()
        if name not in replies:
            ctx.telegram.reply(message, "Такого быстрого ответа нет.")
            return
        del replies[name]
        save_replies(replies)
        ctx.telegram.reply(message, f"✅ «{name}» удалён.")

    @ctx.telegram.command("freply_list")
    def cmd_list(message):
        ctx.telegram.reply(message, build_list_text() + "\n\nОтправить: <code>/freply имя chat_id</code>")

    @ctx.telegram.command("freply")
    def cmd_send(message):
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            ctx.telegram.reply(message, "Использование: /freply [имя] [chat_id]")
            return
        name, chat_id = parts[1], parts[2].strip()
        replies = get_replies()
        if name not in replies:
            ctx.telegram.reply(message, "Такого быстрого ответа нет.")
            return
        try:
            ctx.account.send_message(chat_id, replies[name])
        except Exception as e:
            ctx.telegram.reply(message, f"❌ Не удалось отправить: {e}")
            return
        ctx.telegram.reply(message, "✅ Отправлено.")

    SECTION = "⚡ Быстрые ответы"

    @ctx.telegram.menu_item(SECTION, "📋 Список", "freply:list", group="УПРАВЛЕНИЕ")
    def cbq_list(call):
        ctx.telegram.bot.send_message(call.message.chat.id, build_list_text())

    @ctx.telegram.menu_item(SECTION, "➕ Добавить", "freply:add_ask", group="НАСТРОЙКИ")
    def cbq_add_ask(call):
        def on_name(msg):
            name = msg.text.strip()

            def on_text(msg2):
                replies = get_replies()
                replies[name] = msg2.text
                save_replies(replies)
                ctx.telegram.bot.send_message(msg2.chat.id, f"✅ Быстрый ответ «{name}» сохранён.")

            ctx.telegram.ask(msg.chat.id, msg.from_user.id, "Теперь пришлите текст ответа.", on_text)

        ctx.telegram.ask(call.message.chat.id, call.from_user.id, "Пришлите имя быстрого ответа.", on_name)

    @ctx.telegram.menu_item(SECTION, "📤 Отправить", "freply:send_ask", group="УПРАВЛЕНИЕ")
    def cbq_send_ask(call):
        def on_name(msg):
            name = msg.text.strip()
            replies = get_replies()
            if name not in replies:
                ctx.telegram.bot.send_message(msg.chat.id, "Такого быстрого ответа нет.")
                return

            def on_chat_id(msg2):
                try:
                    ctx.account.send_message(msg2.text.strip(), replies[name])
                    ctx.telegram.bot.send_message(msg2.chat.id, "✅ Отправлено.")
                except Exception as e:
                    ctx.telegram.bot.send_message(msg2.chat.id, f"❌ Не удалось отправить: {e}")

            ctx.telegram.ask(msg.chat.id, msg.from_user.id, "Теперь пришлите ID чата.", on_chat_id)

        ctx.telegram.ask(call.message.chat.id, call.from_user.id, "Пришлите имя быстрого ответа.", on_name)

    @ctx.telegram.menu_item(SECTION, "🗑 Удалить", "freply:remove_ask", group="НАСТРОЙКИ")
    def cbq_remove_ask(call):
        def on_name(msg):
            name = msg.text.strip()
            replies = get_replies()
            if name not in replies:
                ctx.telegram.bot.send_message(msg.chat.id, "Такого быстрого ответа нет.")
                return
            del replies[name]
            save_replies(replies)
            ctx.telegram.bot.send_message(msg.chat.id, f"✅ «{name}» удалён.")

        ctx.telegram.ask(call.message.chat.id, call.from_user.id, "Пришлите имя быстрого ответа для удаления.", on_name)
