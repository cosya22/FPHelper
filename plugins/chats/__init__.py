"""Просмотр чатов и ответ покупателям прямо из Telegram."""

from fphelper import PluginInfo

INFO = PluginInfo(
    name="Chats",
    version="1.0.0",
    description="/chats — список чатов, /reply <chat_id> <текст> — ответить.",
    author="you",
)

MAX_CHATS_SHOWN = 15
MAX_HISTORY_SHOWN = 10


def setup(ctx):
    @ctx.telegram.command("chats")
    def cmd_chats(message):
        try:
            chats = ctx.account.get_chats(update=True)
        except Exception as e:
            ctx.telegram.reply(message, f"❌ Не удалось получить чаты: {e}")
            return
        if not chats:
            ctx.telegram.reply(message, "Чатов пока нет.")
            return
        lines = ["<b>Последние чаты:</b>\n"]
        for chat_id, chat in list(chats.items())[:MAX_CHATS_SHOWN]:
            preview = (chat.last_message_text or "").strip().replace("\n", " ")[:60]
            lines.append(f"• <code>{chat_id}</code> {chat.name} — {preview}")
        lines.append("\nОтветить: <code>/reply chat_id текст</code>")
        lines.append("История: <code>/history chat_id</code>")
        ctx.telegram.reply(message, "\n".join(lines))

    @ctx.telegram.command("history")
    def cmd_history(message):
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            ctx.telegram.reply(message, "Использование: /history <chat_id>")
            return
        chat_id = parts[1].strip()
        try:
            history = ctx.account.get_chat_history(chat_id)
        except Exception as e:
            ctx.telegram.reply(message, f"❌ Не удалось получить историю: {e}")
            return
        if not history:
            ctx.telegram.reply(message, "Сообщений нет.")
            return
        lines = [f"<b>Последние сообщения (чат {chat_id}):</b>\n"]
        for m in history[-MAX_HISTORY_SHOWN:]:
            author = m.author or "?"
            text = (m.text or "[изображение]").replace("\n", " ")[:150]
            lines.append(f"<b>{author}:</b> {text}")
        ctx.telegram.reply(message, "\n".join(lines))

    @ctx.telegram.command("reply")
    def cmd_reply(message):
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            ctx.telegram.reply(message, "Использование: /reply <chat_id> <текст>")
            return
        chat_id, text = parts[1], parts[2]
        try:
            ctx.account.send_message(chat_id, text)
        except Exception as e:
            ctx.telegram.reply(message, f"❌ Не удалось отправить: {e}")
            return
        ctx.telegram.reply(message, "✅ Отправлено.")
