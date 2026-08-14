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
    version="1.0.0",
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
                ctx.notify_admins(f"💸 Авто-вывод выполнен: {amount} {state['currency']} → {state['wallet']}")
                ctx.logger.info(f"Авто-вывод выполнен: {result}")
            except Exception as e:
                ctx.notify_admins(f"❌ Авто-вывод не удался: {e}")
                ctx.logger.exception("Ошибка авто-вывода")
                state["last_withdrawal_at"] = now  # не долбим сайт каждые 5 минут после ошибки
                save_state(state)

    threading.Thread(target=worker, daemon=True).start()

    @ctx.telegram.command("withdrawal_status")
    def cmd_status(message):
        state = get_state()
        status = "включён ✅" if state["enabled"] else "выключен ⛔"
        text = (
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
        ctx.telegram.reply(message, text)

    @ctx.telegram.command("withdrawal_setup")
    def cmd_setup(message):
        parts = message.text.split(maxsplit=5)
        if len(parts) < 6:
            ctx.telegram.reply(
                message,
                "Использование: /withdrawal_setup <валюта> <кошелёк> <адрес> <сумма|all> <интервал_часов>",
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

        state = get_state()
        state.update(
            currency=currency_raw.upper(),
            wallet=wallet_raw.upper(),
            address=address,
            amount_mode=amount_raw.lower() if amount_raw.lower() == "all" else amount_raw,
            interval_hours=interval_hours,
        )
        save_state(state)
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
