"""Просмотр чатов и ответ покупателям прямо из Telegram."""

import io

from fphelper import PluginInfo, blacklist

INFO = PluginInfo(
    name="Chats",
    version="1.2.0",
    description="/chats — список чатов, /reply [chat_id] [текст] — ответить, отправка картинок через меню.",
    author="you",
)

SECTION = "💬 Чаты"
MAX_CHATS_SHOWN = 15
MAX_HISTORY_SHOWN = 10


def setup(ctx):
    def build_chats_text():
        chats = ctx.account.get_chats(update=True)
        if not chats:
            return "Чатов пока нет."
        lines = ["<b>Последние чаты:</b>\n"]
        for chat_id, chat in list(chats.items())[:MAX_CHATS_SHOWN]:
            preview = (chat.last_message_text or "").strip().replace("\n", " ")[:60]
            lines.append(f"• <code>{chat_id}</code> {chat.name} — {preview}")
        return "\n".join(lines)

    def build_history_text(chat_id):
        history = ctx.account.get_chat_history(chat_id)
        if not history:
            return "Сообщений нет."
        lines = [f"<b>Последние сообщения (чат {chat_id}):</b>\n"]
        for m in history[-MAX_HISTORY_SHOWN:]:
            author = m.author or "?"
            text = (m.text or "[изображение]").replace("\n", " ")[:150]
            lines.append(f"<b>{author}:</b> {text}")
        return "\n".join(lines)

    @ctx.events.new_message
    def on_message_notify(event):
        message = event.message
        if message.author_id == ctx.account.id or not message.text:
            return
        if blacklist.is_restricted(message.author, "no_message_notify"):
            return
        preview = message.text.replace("\n", " ")[:200]
        ctx.notify_owner(f"💬 {message.author}: {preview}", event_type="new_message")

    @ctx.telegram.command("chats")
    def cmd_chats(message):
        try:
            text = build_chats_text() + "\n\nОтветить: <code>/reply chat_id текст</code>\nИстория: <code>/history chat_id</code>"
        except Exception as e:
            ctx.telegram.reply(message, f"❌ Не удалось получить чаты: {e}")
            return
        ctx.telegram.reply(message, text)

    @ctx.telegram.command("history")
    def cmd_history(message):
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            ctx.telegram.reply(message, "Использование: /history <chat_id>")
            return
        try:
            text = build_history_text(parts[1].strip())
        except Exception as e:
            ctx.telegram.reply(message, f"❌ Не удалось получить историю: {e}")
            return
        ctx.telegram.reply(message, text)

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

    @ctx.telegram.menu_item(SECTION, "📋 Список чатов", "chats:list")
    def cbq_list(call):
        try:
            text = build_chats_text()
        except Exception as e:
            text = f"❌ Не удалось получить чаты: {e}"
        ctx.telegram.bot.send_message(call.message.chat.id, text)

    @ctx.telegram.menu_item(SECTION, "📜 История чата", "chats:history_ask")
    def cbq_history_ask(call):
        def on_chat_id(msg):
            try:
                text = build_history_text(msg.text.strip())
            except Exception as e:
                text = f"❌ Не удалось получить историю: {e}"
            ctx.telegram.bot.send_message(msg.chat.id, text)

        ctx.telegram.ask(call.message.chat.id, call.from_user.id, "Пришлите ID чата.", on_chat_id)

    @ctx.telegram.menu_item(SECTION, "✍️ Ответить в чат", "chats:reply_ask")
    def cbq_reply_ask(call):
        def on_chat_id(msg):
            chat_id = msg.text.strip()

            def on_text(msg2):
                try:
                    ctx.account.send_message(chat_id, msg2.text)
                    ctx.telegram.bot.send_message(msg2.chat.id, "✅ Отправлено.")
                except Exception as e:
                    ctx.telegram.bot.send_message(msg2.chat.id, f"❌ Не удалось отправить: {e}")

            ctx.telegram.ask(msg.chat.id, msg.from_user.id, "Теперь пришлите текст ответа.", on_text)

        ctx.telegram.ask(call.message.chat.id, call.from_user.id, "Пришлите ID чата.", on_chat_id)

    @ctx.telegram.menu_item(SECTION, "🖼️ Отправить картинку", "chats:image_ask")
    def cbq_image_ask(call):
        def on_chat_id(msg):
            chat_id = msg.text.strip()

            def on_photo(msg2):
                photo = getattr(msg2, "photo", None)
                if not photo:
                    ctx.telegram.bot.send_message(msg2.chat.id, "Это не похоже на фото. Отменено, попробуйте ещё раз кнопкой.")
                    return
                try:
                    file_info = ctx.telegram.bot.get_file(photo[-1].file_id)
                    downloaded = ctx.telegram.bot.download_file(file_info.file_path)
                    image_id = ctx.account.upload_image(io.BytesIO(downloaded))
                    ctx.account.send_image(chat_id, image_id)
                    ctx.telegram.bot.send_message(msg2.chat.id, "✅ Картинка отправлена.")
                except Exception as e:
                    ctx.telegram.bot.send_message(msg2.chat.id, f"❌ Не удалось отправить картинку: {e}")

            ctx.telegram.ask(msg.chat.id, msg.from_user.id, "Теперь пришлите саму картинку.", on_photo)

        ctx.telegram.ask(call.message.chat.id, call.from_user.id, "Пришлите ID чата, куда отправить картинку.", on_chat_id)
