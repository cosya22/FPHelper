"""
Управление лотами: список активных лотов профиля, просмотр/вкл-выкл/цена по ID.
"""

import html

from fphelper import PluginInfo

INFO = PluginInfo(
    name="Lots",
    version="1.1.0",
    description="/lot [id] — просмотр, /lot_toggle и /lot_price — управление лотом.",
    author="you",
)

SECTION = "🛍️ Лоты"


def setup(ctx):
    def build_lot_text(lot_id):
        fields = ctx.account.get_lot_fields(lot_id)
        state = "включён ✅" if fields.active else "выключен ⛔"
        return f"<b>Лот {lot_id}</b>\n\nНазвание: {fields.title_ru}\nЦена: {fields.price}\nСтатус: {state}"

    def do_toggle(lot_id):
        fields = ctx.account.get_lot_fields(lot_id)
        fields.active = not fields.active
        fields.renew_fields()
        ctx.account.save_lot(fields)
        return fields.active

    def do_price(lot_id, price):
        fields = ctx.account.get_lot_fields(lot_id)
        fields.price = price
        fields.renew_fields()
        ctx.account.save_lot(fields)

    def build_lots_list_text():
        lots = ctx.account.get_user(ctx.account.id).get_lots()
        if not lots:
            return "Активных лотов не найдено."
        lines = [f"<b>Активные лоты ({len(lots)}):</b>\n"]
        for lot in lots:
            title = html.escape(lot.description or lot.subcategory.name)
            server = f", {html.escape(lot.server)}" if lot.server else ""
            lines.append(f"🔹 <code>{lot.id}</code> {title}{server} — {lot.price}")
        return "\n".join(lines)

    @ctx.telegram.command("lots")
    def cmd_lots(message):
        try:
            text = build_lots_list_text()
        except Exception as e:
            ctx.telegram.reply(message, f"❌ Не удалось получить список лотов: {e}")
            return
        for i in range(0, len(text), 3500):
            ctx.telegram.reply(message, text[i:i + 3500])

    @ctx.telegram.menu_item(SECTION, "📋 Мои лоты", "lots:list")
    def cbq_list(call):
        try:
            text = build_lots_list_text()
        except Exception as e:
            ctx.telegram.bot.send_message(call.message.chat.id, f"❌ Не удалось получить список лотов: {e}")
            return
        for i in range(0, len(text), 3500):
            ctx.telegram.bot.send_message(call.message.chat.id, text[i:i + 3500])

    @ctx.telegram.command("lot")
    def cmd_lot(message):
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip().isdigit():
            ctx.telegram.reply(message, "Использование: /lot <lot_id>")
            return
        try:
            text = build_lot_text(int(parts[1].strip()))
        except Exception as e:
            ctx.telegram.reply(message, f"❌ Не удалось получить лот: {e}")
            return
        ctx.telegram.reply(message, text)

    @ctx.telegram.command("lot_toggle")
    def cmd_toggle(message):
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip().isdigit():
            ctx.telegram.reply(message, "Использование: /lot_toggle <lot_id>")
            return
        lot_id = int(parts[1].strip())
        try:
            active = do_toggle(lot_id)
        except Exception as e:
            ctx.telegram.reply(message, f"❌ Не удалось изменить лот: {e}")
            return
        state = "включён ✅" if active else "выключен ⛔"
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
        try:
            do_price(int(parts[1].strip()), price)
        except Exception as e:
            ctx.telegram.reply(message, f"❌ Не удалось изменить цену: {e}")
            return
        ctx.telegram.reply(message, f"✅ Цена лота {parts[1].strip()} изменена на {price}.")

    @ctx.telegram.menu_item(SECTION, "🔍 Лот по ID", "lots:show_ask")
    def cbq_show_ask(call):
        def on_id(msg):
            if not msg.text.strip().isdigit():
                ctx.telegram.bot.send_message(msg.chat.id, "ID должен быть числом.")
                return
            try:
                text = build_lot_text(int(msg.text.strip()))
            except Exception as e:
                text = f"❌ Не удалось получить лот: {e}"
            ctx.telegram.bot.send_message(msg.chat.id, text)

        ctx.telegram.ask(call.message.chat.id, call.from_user.id, "Пришлите ID лота.", on_id)

    @ctx.telegram.menu_item(SECTION, "🔄 Вкл/выкл лота", "lots:toggle_ask")
    def cbq_toggle_ask(call):
        def on_id(msg):
            if not msg.text.strip().isdigit():
                ctx.telegram.bot.send_message(msg.chat.id, "ID должен быть числом.")
                return
            lot_id = int(msg.text.strip())
            try:
                active = do_toggle(lot_id)
                state = "включён ✅" if active else "выключен ⛔"
                ctx.telegram.bot.send_message(msg.chat.id, f"Лот {lot_id} теперь {state}.")
            except Exception as e:
                ctx.telegram.bot.send_message(msg.chat.id, f"❌ Не удалось изменить лот: {e}")

        ctx.telegram.ask(call.message.chat.id, call.from_user.id, "Пришлите ID лота для вкл/выкл.", on_id)

    @ctx.telegram.menu_item(SECTION, "💲 Изменить цену", "lots:price_ask")
    def cbq_price_ask(call):
        def on_id(msg):
            if not msg.text.strip().isdigit():
                ctx.telegram.bot.send_message(msg.chat.id, "ID должен быть числом.")
                return
            lot_id = int(msg.text.strip())

            def on_price(msg2):
                try:
                    price = float(msg2.text.strip().replace(",", "."))
                except ValueError:
                    ctx.telegram.bot.send_message(msg2.chat.id, "Цена должна быть числом.")
                    return
                try:
                    do_price(lot_id, price)
                    ctx.telegram.bot.send_message(msg2.chat.id, f"✅ Цена лота {lot_id} изменена на {price}.")
                except Exception as e:
                    ctx.telegram.bot.send_message(msg2.chat.id, f"❌ Не удалось изменить цену: {e}")

            ctx.telegram.ask(msg.chat.id, msg.from_user.id, "Теперь пришлите новую цену.", on_price)

        ctx.telegram.ask(call.message.chat.id, call.from_user.id, "Пришлите ID лота для изменения цены.", on_id)
