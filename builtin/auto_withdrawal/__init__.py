"""
Авто-вывод средств с баланса FunPay по расписанию. Выключен по умолчанию — включается
только явной командой с указанием валюты, кошелька, адреса и суммы. Двигает реальные
деньги, поэтому: сначала проверьте настройки командой /withdrawal_status, затем включайте.
"""

import threading
import time

from fphelper import PluginInfo
from FunPayAPI.common.enums import Currency, Wallet

INFO = PluginInfo(
    name="Auto Withdrawal",
    version="1.2.0",
    description="Периодический вывод средств с баланса FunPay (выключен по умолчанию).",
    author="you",
)

CHECK_INTERVAL = 300  # секунд между проверками, не пора ли выводить


def setup(ctx):
    def get_state():
        state = ctx.storage.all()
        state.setdefault("enabled", False)
        state.setdefault("currency", None)
        state.setdefault("wallet", None)
        state.setdefault("address", None)
        state.setdefault("amount_mode", "all")  # "all" или число строкой
        state.setdefault("interval_hours", 24)
        state.setdefault("last_withdrawal_at", 0)
        return state

    def save_state(state):
        ctx.storage.update(state)

    def worker():
        while True:
            time.sleep(CHECK_INTERVAL)
            state = get_state()
            if not state["enabled"] or not state["currency"] or not state["wallet"] or not state["address"]:
                continue

            now = time.time()
            next_at = state["last_withdrawal_at"] + state["interval_hours"] * 3600
            if now < next_at:
                continue

            try:
                ctx.account.get()  # обновляем total_balance перед выводом
                if state["amount_mode"] == "all":
                    amount = ctx.account.total_balance
                else:
                    amount = float(state["amount_mode"])

                if amount <= 0:
                    ctx.logger.info("Вывод пропущен: сумма к выводу 0")
                    state["last_withdrawal_at"] = now
                    save_state(state)
                    continue

                currency = Currency[state["currency"]]
                wallet = Wallet[state["wallet"]]
                result = ctx.account.withdraw(currency, wallet, amount, state["address"])
                state["last_withdrawal_at"] = now
                save_state(state)
                ctx.notify_owner(f"💸 Авто-вывод выполнен: {amount} {state['currency']} → {state['wallet']}")
                ctx.logger.info(f"Авто-вывод выполнен: {result}")
            except Exception as e:
                ctx.notify_owner(f"❌ Авто-вывод не удался: {e}")
                ctx.logger.exception("Ошибка авто-вывода")
                state["last_withdrawal_at"] = now  # не долбим сайт каждые 5 минут после ошибки
                save_state(state)

    threading.Thread(target=worker, daemon=True).start()

    def build_status_text():
        state = get_state()
        status = "включён ✅" if state["enabled"] else "выключен ⛔"
        return (
            f"<b>Авто-вывод</b>: {status}\n\n"
            f"Валюта: {state['currency'] or '—'}\n"
            f"Кошелёк: {state['wallet'] or '—'}\n"
            f"Адрес: <code>{state['address'] or '—'}</code>\n"
            f"Сумма: {state['amount_mode']}\n"
            f"Интервал: {state['interval_hours']} ч.\n\n"
            "Настроить: <code>/withdrawal_setup валюта кошелёк адрес сумма интервал_часов</code>\n"
            f"Валюты: {', '.join(c.name for c in Currency)}\n"
            f"Кошельки: {', '.join(w.name for w in Wallet)}\n"
            "Сумма — число или <code>all</code> (весь баланс)\n\n"
            "/withdrawal_on — включить · /withdrawal_off — выключить"
        )

    def apply_setup(currency_raw, wallet_raw, address, amount_raw, interval_hours):
        state = get_state()
        state.update(
            currency=currency_raw.upper(),
            wallet=wallet_raw.upper(),
            address=address,
            amount_mode=amount_raw.lower() if amount_raw.lower() == "all" else amount_raw,
            interval_hours=interval_hours,
        )
        save_state(state)

    @ctx.telegram.command("withdrawal_status")
    def cmd_status(message):
        ctx.telegram.reply(message, build_status_text())

    @ctx.telegram.command("withdrawal_setup")
    def cmd_setup(message):
        parts = message.text.split(maxsplit=5)
        if len(parts) < 6:
            ctx.telegram.reply(
                message,
                "Использование: /withdrawal_setup [валюта] [кошелёк] [адрес] [сумма|all] [интервал_часов]",
            )
            return
        _, currency_raw, wallet_raw, address, amount_raw, interval_raw = parts
        if currency_raw.upper() not in Currency.__members__:
            ctx.telegram.reply(message, f"Неизвестная валюта. Варианты: {', '.join(Currency.__members__)}")
            return
        if wallet_raw.upper() not in Wallet.__members__:
            ctx.telegram.reply(message, f"Неизвестный кошелёк. Варианты: {', '.join(Wallet.__members__)}")
            return
        if amount_raw.lower() != "all":
            try:
                float(amount_raw)
            except ValueError:
                ctx.telegram.reply(message, "Сумма должна быть числом или 'all'.")
                return
        try:
            interval_hours = float(interval_raw)
        except ValueError:
            ctx.telegram.reply(message, "Интервал должен быть числом (часы).")
            return

        apply_setup(currency_raw, wallet_raw, address, amount_raw, interval_hours)
        ctx.telegram.reply(
            message,
            "✅ Настройки сохранены. Проверьте их через /withdrawal_status и включите /withdrawal_on, когда будете готовы.",
        )

    @ctx.telegram.command("withdrawal_on")
    def cmd_on(message):
        state = get_state()
        if not state["currency"] or not state["wallet"] or not state["address"]:
            ctx.telegram.reply(message, "Сначала настройте вывод: /withdrawal_setup ...")
            return
        state["enabled"] = True
        save_state(state)
        ctx.telegram.reply(message, "✅ Авто-вывод включён.")

    @ctx.telegram.command("withdrawal_off")
    def cmd_off(message):
        state = get_state()
        state["enabled"] = False
        save_state(state)
        ctx.telegram.reply(message, "⛔ Авто-вывод выключен.")

    SECTION = "💸 Авто-вывод"

    @ctx.telegram.menu_item(SECTION, "📊 Статус", "withdrawal:status", group="УПРАВЛЕНИЕ")
    def cbq_status(call):
        ctx.telegram.bot.send_message(call.message.chat.id, build_status_text())

    @ctx.telegram.menu_item(SECTION, "⚙️ Настроить", "withdrawal:setup_ask", group="НАСТРОЙКИ")
    def cbq_setup_ask(call):
        def on_currency(msg):
            currency_raw = msg.text.strip()
            if currency_raw.upper() not in Currency.__members__:
                ctx.telegram.bot.send_message(msg.chat.id, f"Неизвестная валюта. Варианты: {', '.join(Currency.__members__)}")
                return

            def on_wallet(msg2):
                wallet_raw = msg2.text.strip()
                if wallet_raw.upper() not in Wallet.__members__:
                    ctx.telegram.bot.send_message(msg2.chat.id, f"Неизвестный кошелёк. Варианты: {', '.join(Wallet.__members__)}")
                    return

                def on_address(msg3):
                    address = msg3.text.strip()

                    def on_amount(msg4):
                        amount_raw = msg4.text.strip()
                        if amount_raw.lower() != "all":
                            try:
                                float(amount_raw)
                            except ValueError:
                                ctx.telegram.bot.send_message(msg4.chat.id, "Сумма должна быть числом или 'all'.")
                                return

                        def on_interval(msg5):
                            try:
                                interval_hours = float(msg5.text.strip())
                            except ValueError:
                                ctx.telegram.bot.send_message(msg5.chat.id, "Интервал должен быть числом (часы).")
                                return
                            apply_setup(currency_raw, wallet_raw, address, amount_raw, interval_hours)
                            ctx.telegram.bot.send_message(
                                msg5.chat.id,
                                "✅ Настройки сохранены. Проверьте /withdrawal_status и включите вывод отдельной кнопкой.",
                            )

                        ctx.telegram.ask(msg4.chat.id, msg4.from_user.id, "Интервал между выводами в часах?", on_interval)

                    ctx.telegram.ask(
                        msg3.chat.id, msg3.from_user.id,
                        "Сумма к выводу — число или 'all' (весь баланс)?", on_amount,
                    )

                ctx.telegram.ask(msg2.chat.id, msg2.from_user.id, "Адрес/реквизиты для вывода?", on_address)

            ctx.telegram.ask(
                msg.chat.id, msg.from_user.id,
                f"Кошелёк? Варианты: {', '.join(Wallet.__members__)}", on_wallet,
            )

        ctx.telegram.ask(
            call.message.chat.id, call.from_user.id,
            f"Валюта? Варианты: {', '.join(Currency.__members__)}", on_currency,
        )

    def toggle_label():
        return "🟢 Авто-вывод" if get_state()["enabled"] else "🔴 Авто-вывод"

    @ctx.telegram.menu_item(SECTION, toggle_label, "withdrawal:toggle", group="НАСТРОЙКИ")
    def cbq_toggle(call):
        state = get_state()
        if not state["enabled"] and (not state["currency"] or not state["wallet"] or not state["address"]):
            ctx.telegram.bot.send_message(call.message.chat.id, "Сначала настройте вывод кнопкой «⚙️ Настроить».")
            return
        state["enabled"] = not state["enabled"]
        save_state(state)
        ctx.telegram.refresh_section(call, SECTION)
