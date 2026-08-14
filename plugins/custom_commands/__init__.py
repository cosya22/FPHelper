"""
Свои команды для покупателей: если покупатель пишет в чат «!имя_команды»,
бот отвечает заранее заданным текстом. Поддерживается плейсхолдер {username}.
"""

from fphelper import PluginInfo

INFO = PluginInfo(
    name="Custom Commands",
    version="1.0.0",
    description="Покупатель пишет !команда в чате — бот отвечает заданным текстом.",
    author="you",
)


def setup(ctx):
    def get_commands():
        return ctx.storage.get("commands", {})

    def save_commands(commands):
        ctx.storage.set("commands", commands)

    def build_list_text():
        commands = get_commands()
        if not commands:
            return "Своих команд пока нет."
        lines = ["<b>Команды для покупателей:</b>\n"]
        for name, text in commands.items():
            lines.append(f"• <b>!{name}</b> — {text[:50]}")
        return "\n".join(lines)

    @ctx.events.new_message
    def on_message(event):
        message = event.message
        if message.author_id == ctx.account.id or not message.text:
            return
        text = message.text.strip()
        if not text.startswith("!"):
            return
        name = text[1:].split()[0].lower() if len(text) > 1 else ""
        commands = get_commands()
        if name not in commands:
            return
        reply = commands[name].format(username=message.author or "")
        try:
            ctx.account.send_message(message.chat_id, reply)
        except Exception:
            ctx.logger.exception(f"Не удалось ответить на команду !{name}")

    @ctx.telegram.command("cmd_add")
    def cmd_add(message):
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            ctx.telegram.reply(
                message,
                "Использование: /cmd_add <имя> <текст>\n"
                "В тексте можно использовать {username} — имя покупателя подставится автоматически.",
            )
            return
        name, text = parts[1].lower(), parts[2]
        commands = get_commands()
        commands[name] = text
        save_commands(commands)
        ctx.telegram.reply(message, f"✅ Команда «!{name}» сохранена.")

    @ctx.telegram.command("cmd_remove")
    def cmd_remove(message):
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            ctx.telegram.reply(message, "Использование: /cmd_remove <имя>")
            return
        name = parts[1].strip().lower()
        commands = get_commands()
        if name not in commands:
            ctx.telegram.reply(message, "Такой команды нет.")
            return
        del commands[name]
        save_commands(commands)
        ctx.telegram.reply(message, f"✅ Команда «!{name}» удалена.")

    @ctx.telegram.command("cmd_list")
    def cmd_list(message):
        ctx.telegram.reply(message, build_list_text())

    SECTION = "❗ Команды"

    @ctx.telegram.menu_item(SECTION, "📋 Список", "cmd:list")
    def cbq_list(call):
        ctx.telegram.bot.send_message(call.message.chat.id, build_list_text())

    @ctx.telegram.menu_item(SECTION, "➕ Добавить", "cmd:add_ask")
    def cbq_add_ask(call):
        def on_name(msg):
            name = msg.text.strip().lower()

            def on_text(msg2):
                commands = get_commands()
                commands[name] = msg2.text
                save_commands(commands)
                ctx.telegram.bot.send_message(msg2.chat.id, f"✅ Команда «!{name}» сохранена.")

            ctx.telegram.ask(
                msg.chat.id, msg.from_user.id,
                "Теперь пришлите текст ответа (можно использовать {username}).",
                on_text,
            )

        ctx.telegram.ask(call.message.chat.id, call.from_user.id, "Пришлите имя команды (без !).", on_name)

    @ctx.telegram.menu_item(SECTION, "🗑 Удалить", "cmd:remove_ask")
    def cbq_remove_ask(call):
        def on_name(msg):
            name = msg.text.strip().lower()
            commands = get_commands()
            if name not in commands:
                ctx.telegram.bot.send_message(msg.chat.id, "Такой команды нет.")
                return
            del commands[name]
            save_commands(commands)
            ctx.telegram.bot.send_message(msg.chat.id, f"✅ Команда «!{name}» удалена.")

        ctx.telegram.ask(call.message.chat.id, call.from_user.id, "Пришлите имя команды для удаления (без !).", on_name)
