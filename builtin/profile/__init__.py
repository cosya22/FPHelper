"""Просмотр профиля аккаунта FunPay прямо из Telegram."""

from fphelper import PluginInfo

INFO = PluginInfo(
    name="Profile",
    version="1.0.0",
    description="/profile — баланс, валюта, активные продажи/покупки.",
    author="you",
)


def setup(ctx):
    def build_text():
        acc = ctx.account
        currency = getattr(acc.currency, "name", acc.currency)
        return (
            f"<b>👤 {acc.username}</b> (ID {acc.id})\n\n"
            f"💰 Баланс: <code>{acc.total_balance}</code> {currency}\n"
            f"🛒 Активные продажи: <code>{acc.active_sales}</code>\n"
            f"🛍️ Активные покупки: <code>{acc.active_purchases}</code>"
        )

    @ctx.telegram.command("profile")
    def cmd_profile(message):
        ctx.telegram.reply(message, build_text())

    @ctx.telegram.menu_item("👤 Профиль", "👤 Показать профиль", "profile:show")
    def cbq_profile(call):
        ctx.telegram.bot.send_message(call.message.chat.id, build_text())
