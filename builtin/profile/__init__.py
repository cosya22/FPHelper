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
        # Account не хранит баланс/валюту сам по себе (нет .currency/.total_balance) —
        # баланс сразу в 3 валютах отдаёт отдельный запрос get_balance().
        try:
            balance = acc.get_balance()
            balance_line = (
                f"💰 Баланс: <code>{balance.total_rub:.2f}</code> RUB · "
                f"<code>{balance.total_usd:.2f}</code> USD · <code>{balance.total_eur:.2f}</code> EUR"
            )
        except Exception:
            balance_line = "💰 Баланс: не удалось получить"
        return (
            f"<b>👤 {acc.username}</b> (ID {acc.id})\n\n"
            f"{balance_line}\n"
            f"🛒 Активные продажи: <code>{acc.active_sales}</code>\n"
            f"🛍️ Активные покупки: <code>{acc.active_purchases}</code>"
        )

    @ctx.telegram.command("profile")
    def cmd_profile(message):
        ctx.telegram.reply(message, build_text())

    @ctx.telegram.menu_item("👤 Профиль", "👤 Показать профиль", "profile:show")
    def cbq_profile(call):
        ctx.telegram.bot.send_message(call.message.chat.id, build_text())
