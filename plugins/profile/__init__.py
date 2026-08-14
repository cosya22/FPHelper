"""Просмотр профиля аккаунта FunPay прямо из Telegram."""

from fphelper import PluginInfo

INFO = PluginInfo(
    name="Profile",
    version="1.0.0",
    description="/profile — баланс, валюта, активные продажи/покупки.",
    author="you",
)


def setup(ctx):
    @ctx.telegram.command("profile")
    def cmd_profile(message):
        acc = ctx.account
        currency = getattr(acc.currency, "name", acc.currency)
        text = (
            f"<b>👤 {acc.username}</b> (ID {acc.id})\n\n"
            f"💰 Баланс: <code>{acc.total_balance}</code> {currency}\n"
            f"🛒 Активные продажи: <code>{acc.active_sales}</code>\n"
            f"🛍️ Активные покупки: <code>{acc.active_purchases}</code>"
        )
        ctx.telegram.reply(message, text)
