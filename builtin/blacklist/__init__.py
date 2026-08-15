"""
Чёрный список покупателей. Сам список и правила ограничений хранятся в
fphelper.blacklist (общий модуль, доступный и другим встроенным модулям —
auto_delivery и custom_commands проверяют его перед выдачей товара/ответом
на команду).
"""

from fphelper import PluginInfo, blacklist

INFO = PluginInfo(
    name="Blacklist",
    version="1.0.0",
    description="Чёрный список покупателей: не выдавать товар, не отвечать на команды, не уведомлять.",
    author="you",
)

SECTION = "🚫 Чёрный список"


def setup(ctx):
    @ctx.telegram.menu_item(SECTION, "📋 Список", "blacklist:list", group="УПРАВЛЕНИЕ")
    def cbq_list(call):
        users = blacklist.list_users()
        if not users:
            ctx.telegram.bot.send_message(call.message.chat.id, "Чёрный список пуст.")
            return
        text = "<b>В чёрном списке:</b>\n\n" + "\n".join(f"• {u}" for u in users)
        ctx.telegram.bot.send_message(call.message.chat.id, text)

    @ctx.telegram.menu_item(SECTION, "➕ Добавить", "blacklist:add_ask", group="НАСТРОЙКИ")
    def cbq_add_ask(call):
        def on_username(msg):
            username = msg.text.strip().lstrip("@")
            if not username:
                ctx.telegram.bot.send_message(msg.chat.id, "Пустой юзернейм, попробуйте снова.")
                return
            if blacklist.add_user(username):
                ctx.telegram.bot.send_message(msg.chat.id, f"✅ {username} добавлен в чёрный список.")
            else:
                ctx.telegram.bot.send_message(msg.chat.id, f"{username} уже в чёрном списке.")

        ctx.telegram.ask(call.message.chat.id, call.from_user.id, "Никнейм покупателя на FunPay?", on_username)

    @ctx.telegram.menu_item(SECTION, "🗑 Убрать", "blacklist:remove_ask", group="НАСТРОЙКИ")
    def cbq_remove_ask(call):
        def on_username(msg):
            username = msg.text.strip().lstrip("@")
            if blacklist.remove_user(username):
                ctx.telegram.bot.send_message(msg.chat.id, f"✅ {username} убран из чёрного списка.")
            else:
                ctx.telegram.bot.send_message(msg.chat.id, f"{username} не найден в чёрном списке.")

        ctx.telegram.ask(call.message.chat.id, call.from_user.id, "Никнейм покупателя, которого убрать?", on_username)

    for key, label in blacklist.RESTRICTIONS.items():
        def make_toggle(key=key, label=label):
            def toggle_label():
                on = blacklist.get_restriction(key)
                return f"🟢 {label}" if on else f"🔴 {label}"
            return toggle_label

        def make_handler(key=key):
            def cbq_toggle(call):
                blacklist.set_restriction(key, not blacklist.get_restriction(key))
                ctx.telegram.refresh_section(call, SECTION)
            return cbq_toggle

        ctx.telegram.menu_item(SECTION, make_toggle(), f"blacklist:toggle:{key}", group="НАСТРОЙКИ")(make_handler())
