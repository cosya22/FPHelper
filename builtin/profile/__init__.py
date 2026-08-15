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
        # баланс сразу в 3 валютах отдаёт отдельный запрос get_balance(), которому
        # для запроса нужен ID хоть какого-то существующего лота на FunPay (сам
        # баланс — это баланс залогиненного аккаунта, а не владельца лота).
        # Захардкоженный ID по умолчанию в FunPayAPI мог протухнуть (лот сняли/удалили),
        # поэтому сначала пробуем свой собственный активный лот, если он есть.
        try:
            try:
                own_lots = acc.get_user(acc.id).get_lots()
            except Exception:
                own_lots = []
            lot_id = own_lots[0].id if own_lots else 18853876
            balance = acc.get_balance(lot_id=lot_id)
            balance_line = (
                f"💰 Баланс: <code>{balance.total_rub:.2f}</code> RUB · "
                f"<code>{balance.total_usd:.2f}</code> USD · <code>{balance.total_eur:.2f}</code> EUR"
            )
        except Exception as e:
            balance_line = f"💰 Баланс: не удалось получить ({e})"
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
