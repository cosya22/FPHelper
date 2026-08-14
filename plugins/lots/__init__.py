"""
Управление лотами по ID: просмотр, вкл/выкл, изменение цены.

Официальная FunPayAPI не даёт метода "список моих лотов" — только просмотр/правку
конкретного лота по его ID (ID виден в адресе страницы лота на FunPay, funpay.com/lots/<id>/).
"""

from fphelper import PluginInfo

INFO = PluginInfo(
    name="Lots",
    version="1.0.0",
    description="/lot <id> — просмотр, /lot_toggle и /lot_price — управление лотом.",
    author="you",
)


def setup(ctx):
    @ctx.telegram.command("lot")
    def cmd_lot(message):
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip().isdigit():
            ctx.telegram.reply(message, "Использование: /lot <lot_id>")
            return
        lot_id = int(parts[1].strip())
        try:
            fields = ctx.account.get_lot_fields(lot_id)
        except Exception as e:
            ctx.telegram.reply(message, f"❌ Не удалось получить лот: {e}")
            return
        state = "включён ✅" if fields.active else "выключен ⛔"
        text = (
            f"<b>Лот {lot_id}</b>\n\n"
            f"Название: {fields.title_ru}\n"
            f"Цена: {fields.price}\n"
            f"Статус: {state}"
        )
        ctx.telegram.reply(message, text)

    @ctx.telegram.command("lot_toggle")
    def cmd_toggle(message):
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip().isdigit():
            ctx.telegram.reply(message, "Использование: /lot_toggle <lot_id>")
            return
        lot_id = int(parts[1].strip())
        try:
            fields = ctx.account.get_lot_fields(lot_id)
            fields.active = not fields.active
            fields.renew_fields()
            ctx.account.save_lot(fields)
        except Exception as e:
            ctx.telegram.reply(message, f"❌ Не удалось изменить лот: {e}")
            return
        state = "включён ✅" if fields.active else "выключен ⛔"
        ctx.telegram.reply(message, f"Лот {lot_id} теперь {state}.")

    @ctx.telegram.command("lot_price")
    def cmd_price(message):
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            ctx.telegram.reply(message, "Использование: /lot_price <lot_id> <новая_цена>")
            return
        if not parts[1].strip().isdigit():
            ctx.telegram.reply(message, "lot_id должен быть числом.")
            return
        try:
            price = float(parts[2].strip().replace(",", "."))
        except ValueError:
            ctx.telegram.reply(message, "Цена должна быть числом.")
            return
        lot_id = int(parts[1].strip())
        try:
            fields = ctx.account.get_lot_fields(lot_id)
            fields.price = price
            fields.renew_fields()
            ctx.account.save_lot(fields)
        except Exception as e:
            ctx.telegram.reply(message, f"❌ Не удалось изменить цену: {e}")
            return
        ctx.telegram.reply(message, f"✅ Цена лота {lot_id} изменена на {price}.")
