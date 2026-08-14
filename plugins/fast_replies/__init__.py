"""Быстрые ответы: сохранённые шаблоны текста, которые можно отправить в любой чат одной командой."""

from fphelper import PluginInfo

INFO = PluginInfo(
    name="Fast Replies",
    version="1.0.0",
    description="/freply_add, /freply_list, /freply <имя> <chat_id> — быстрая отправка шаблонов.",
    author="you",
)


def setup(ctx):
    def get_replies():
        return ctx.storage.get("replies", {})

    def save_replies(replies):
        ctx.storage.set("replies", replies)

    @ctx.telegram.command("freply_add")
    def cmd_add(message):
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            ctx.telegram.reply(message, "Использование: /freply_add <имя> <текст>")
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
            ctx.telegram.reply(message, "Использование: /freply_remove <имя>")
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
        replies = get_replies()
        if not replies:
            ctx.telegram.reply(message, "Быстрых ответов пока нет.")
            return
        lines = ["<b>Быстрые ответы:</b>\n"]
        for name, text in replies.items():
            lines.append(f"• <b>{name}</b> — {text[:50]}")
        lines.append("\nОтправить: <code>/freply имя chat_id</code>")
        ctx.telegram.reply(message, "\n".join(lines))

    @ctx.telegram.command("freply")
    def cmd_send(message):
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            ctx.telegram.reply(message, "Использование: /freply <имя> <chat_id>")
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
