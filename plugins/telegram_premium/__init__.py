"""
Авто-выдача Telegram Premium по заказам FunPay через Fragment.com.

Fragment дарит Premium только пакетами на 3, 6 или 12 месяцев — других
вариантов у Telegram нет вообще (проверено на самой странице fragment.com/premium/gift).

Официальный Bot API не умеет дарить Premium за деньги покупателя напрямую
(gift_premium_subscription тратит звёзды самого бота, а не оплату от клиента) —
поэтому используется тот же путь, что и в плагине Telegram Stars: сторонняя
библиотека pyfragment и TON-кошелёк. ЗАВЕДИТЕ ПОД ЭТО ОТДЕЛЬНЫЙ КОШЕЛЁК с
небольшим балансом, не используйте основной. Seed хранится на диске в
зашифрованном виде (crypto.py), но раз к нему обращается сторонняя
библиотека — риск выше, чем у обычного пароля.

Флоу: покупатель оплачивает лот на FunPay (количество = число месяцев: 3, 6
или 12) -> бот просит его Telegram username в чате -> username пойман по
регулярке -> заказ встаёт в очередь -> воркер дарит Premium через Fragment ->
покупателю приходит подтверждение в чат FunPay.

Плюс автопилот, как в Stars: периодически подтягивает цену на Fragment (для
каждого настроенного тарифа отдельно, у 3/6/12 месяцев разная цена не по
линейной формуле) + курс TON/RUB, пересчитывает цену лота с наценкой;
снимает лоты с продажи при нехватке баланса; напоминает покупателю
подтвердить заказ.
"""

import re
import threading
import time

from fphelper import PluginInfo
from pyfragment.exceptions import AlreadySubscribedError, FragmentError, UserNotFoundError
from FunPayAPI.common.enums import OrderStatuses

from . import crypto, fragment_client, pricing

INFO = PluginInfo(
    name="Telegram Premium",
    version="1.1.0",
    description="Авто-выдача Telegram Premium (3/6/12 мес) через Fragment: доставка, динамические цены, авто-лоты, напоминания.",
    author="you",
)

SECTION = "💎 Telegram Premium"
USERNAME_RE = re.compile(r"@([a-zA-Z][a-zA-Z0-9_]{4,31})")
VALID_MONTHS = (3, 6, 12)

STATUS_WAITING_USERNAME = "waiting_username"
STATUS_QUEUED = "queued"
STATUS_DELIVERED = "delivered"
STATUS_FAILED = "failed"

MAX_ATTEMPTS = 3
DELIVERY_CHECK_INTERVAL = 5
PRICE_CHECK_INTERVAL = 300
REMINDER_CHECK_INTERVAL = 1800
REQUIRED_COOKIES = ("stel_ssid", "stel_dt", "stel_token", "stel_ton_token")


def setup(ctx):
    def get_settings():
        s = ctx.storage.get("settings", {})
        s.setdefault("keyword", "premium")
        s.setdefault("enabled", False)
        s.setdefault("seed_enc", None)
        s.setdefault("api_key", None)
        s.setdefault("cookies", None)
        s.setdefault("markup_percent", 20.0)
        s.setdefault("tier_lot_ids", {"3": None, "6": None, "12": None})
        s.setdefault("price_interval_hours", 1.0)
        s.setdefault("min_balance_ton", 0.0)
        s.setdefault("reminder_hours", 24.0)
        s.setdefault("last_price_update", 0)
        return s

    def save_settings(s):
        ctx.storage.set("settings", s)

    def is_configured(s):
        return bool(s["seed_enc"] and s["api_key"] and s["cookies"])

    def get_jobs():
        return ctx.storage.get("jobs", {})

    def save_jobs(jobs):
        ctx.storage.set("jobs", jobs)

    def get_deactivated_lots():
        return set(ctx.storage.get("deactivated_lot_ids", []))

    def save_deactivated_lots(lot_ids):
        ctx.storage.set("deactivated_lot_ids", sorted(lot_ids))

    # ---------- события FunPay: доставка ----------

    @ctx.events.new_order
    def on_order(event):
        order = event.order
        s = get_settings()
        if not s["enabled"] or not is_configured(s):
            return
        if s["keyword"].lower() not in order.description.lower():
            return

        months = int(order.amount or 0)
        if months not in VALID_MONTHS:
            ctx.notify_owner(
                f"⚠️ Заказ {order.id}: количество ({months}) не похоже на 3/6/12 месяцев. "
                f"Выдайте вручную — авто-выдача пропущена."
            )
            return

        try:
            chat = ctx.account.get_chat_by_name(order.buyer_username, make_request=True)
            chat_id = chat.id if chat else order.buyer_username
        except Exception:
            chat_id = order.buyer_username

        jobs = get_jobs()
        jobs[order.id] = {
            "order_id": order.id,
            "buyer_username": order.buyer_username,
            "chat_id": chat_id,
            "months": months,
            "telegram_username": None,
            "status": STATUS_WAITING_USERNAME,
            "attempts": 0,
            "error": None,
            "delivered_at": None,
            "reminded": False,
        }
        save_jobs(jobs)

        try:
            ctx.account.send_message(
                chat_id,
                f"💎 Спасибо за заказ! Пришлите сюда ваш Telegram username (например, @username) — "
                f"подарим Premium на {months} мес.",
            )
        except Exception:
            ctx.logger.exception(f"Не удалось запросить username у {order.buyer_username}")

    @ctx.events.new_message
    def on_message(event):
        message = event.message
        if message.author_id == ctx.account.id or not message.text:
            return
        match = USERNAME_RE.search(message.text)
        if not match:
            return

        jobs = get_jobs()
        job = next(
            (j for j in jobs.values() if j["buyer_username"] == message.author and j["status"] == STATUS_WAITING_USERNAME),
            None,
        )
        if job is None:
            return

        job["telegram_username"] = match.group(1)
        job["status"] = STATUS_QUEUED
        save_jobs(jobs)
        try:
            ctx.account.send_message(message.chat_id, "✅ Принято! 💎 Premium придёт в течение нескольких минут.")
        except Exception:
            pass

    # ---------- воркер доставки ----------

    def delivery_worker():
        while True:
            time.sleep(DELIVERY_CHECK_INTERVAL)
            s = get_settings()
            if not s["enabled"] or not is_configured(s):
                continue

            jobs = get_jobs()
            job = next((j for j in jobs.values() if j["status"] == STATUS_QUEUED), None)
            if job is None:
                continue

            try:
                seed = crypto.decrypt(s["seed_enc"])
                fragment_client.gift_premium_sync(
                    seed, s["api_key"], s["cookies"], f"@{job['telegram_username']}", job["months"]
                )
                job["status"] = STATUS_DELIVERED
                job["delivered_at"] = time.time()
                save_jobs(jobs)
                try:
                    ctx.account.send_message(
                        job["chat_id"], f"✅ Подарили 💎 Premium на {job['months']} мес. Спасибо за покупку!"
                    )
                except Exception:
                    pass
                ctx.notify_owner(
                    f"✅ Заказ {job['order_id']}: выдан Premium на {job['months']} мес. → @{job['telegram_username']}"
                )
            except UserNotFoundError:
                job["status"] = STATUS_WAITING_USERNAME
                job["telegram_username"] = None
                save_jobs(jobs)
                try:
                    ctx.account.send_message(
                        job["chat_id"], "❌ Такого username в Telegram не нашли. Проверьте и пришлите ещё раз."
                    )
                except Exception:
                    pass
            except AlreadySubscribedError:
                job["status"] = STATUS_FAILED
                job["error"] = "У покупателя уже есть Telegram Premium"
                save_jobs(jobs)
                try:
                    ctx.account.send_message(
                        job["chat_id"],
                        "⚠️ У вас уже активен Telegram Premium — Fragment не позволяет подарить поверх "
                        "действующей подписки. Напишите продавцу, разберёмся вручную.",
                    )
                except Exception:
                    pass
                ctx.notify_owner(f"⚠️ Заказ {job['order_id']}: у покупателя уже есть Premium — нужна ручная обработка (возврат?).")
            except FragmentError as e:
                job["attempts"] += 1
                if job["attempts"] >= MAX_ATTEMPTS:
                    job["status"] = STATUS_FAILED
                    job["error"] = str(e)
                    ctx.notify_owner(f"❌ Заказ {job['order_id']}: не удалось выдать Premium — {e}")
                save_jobs(jobs)
            except Exception:
                ctx.logger.exception(f"Неожиданная ошибка при выдаче заказа {job['order_id']}")
                job["attempts"] += 1
                if job["attempts"] >= MAX_ATTEMPTS:
                    job["status"] = STATUS_FAILED
                save_jobs(jobs)

    threading.Thread(target=delivery_worker, daemon=True).start()

    # ---------- воркер цены и баланса ----------

    def apply_lot_price(lot_id, price_rub):
        fields = ctx.account.get_lot_fields(lot_id)
        fields.price = round(price_rub, 2)
        fields.renew_fields()
        ctx.account.save_lot(fields)

    def set_lot_active(lot_id, active):
        fields = ctx.account.get_lot_fields(lot_id)
        fields.active = active
        fields.renew_fields()
        ctx.account.save_lot(fields)

    def configured_tier_lots(s):
        return [(int(months_str), lot_id) for months_str, lot_id in s["tier_lot_ids"].items() if lot_id]

    def price_and_balance_worker():
        while True:
            time.sleep(PRICE_CHECK_INTERVAL)
            s = get_settings()
            tiers = configured_tier_lots(s)
            if not s["enabled"] or not is_configured(s) or not tiers:
                continue

            now = time.time()
            interval = s["price_interval_hours"] * 3600
            if now - s["last_price_update"] < interval:
                continue

            try:
                seed = crypto.decrypt(s["seed_enc"])
                ton_rub = pricing.get_ton_rub_rate()
            except Exception as e:
                ctx.logger.exception("Не удалось получить курс TON/RUB")
                ctx.notify_owner(f"⚠️ Telegram Premium: не удалось обновить цену — {e}")
                continue

            deactivated = get_deactivated_lots()
            changed_deactivated = False
            min_balance = s["min_balance_ton"]
            last_balance = None

            for months, lot_id in tiers:
                try:
                    price_ton, balance_ton = pricing.quote_premium_price_and_balance_sync(
                        seed, s["api_key"], s["cookies"], months
                    )
                    last_balance = balance_ton
                    price_rub = price_ton * ton_rub * (1 + s["markup_percent"] / 100)

                    if min_balance > 0:
                        if balance_ton < min_balance:
                            if lot_id not in deactivated:
                                set_lot_active(lot_id, False)
                                deactivated.add(lot_id)
                                changed_deactivated = True
                                ctx.notify_owner(
                                    f"⏸ Лот {lot_id} ({months} мес.) снят с продажи: баланс кошелька "
                                    f"({balance_ton:.2f} TON) ниже порога ({min_balance} TON)."
                                )
                            continue
                        elif lot_id in deactivated:
                            set_lot_active(lot_id, True)
                            deactivated.discard(lot_id)
                            changed_deactivated = True
                            ctx.notify_owner(f"▶️ Лот {lot_id} ({months} мес.) снова в продаже: баланс восстановлен.")

                    apply_lot_price(lot_id, price_rub)
                    ctx.logger.info(f"Цена Premium {months} мес обновлена: {price_rub:.2f} RUB")
                except Exception as e:
                    ctx.logger.exception(f"Не удалось обновить лот {lot_id} ({months} мес.)")
                    ctx.notify_owner(f"⚠️ Лот {lot_id} ({months} мес.): не удалось обновить — {e}")

            if changed_deactivated:
                save_deactivated_lots(deactivated)

            if last_balance is not None:
                s = get_settings()
                s["last_price_update"] = now
                save_settings(s)

    threading.Thread(target=price_and_balance_worker, daemon=True).start()

    # ---------- напоминания о неподтверждённых заказах ----------

    def reminder_worker():
        while True:
            time.sleep(REMINDER_CHECK_INTERVAL)
            s = get_settings()
            if s["reminder_hours"] <= 0:
                continue

            jobs = get_jobs()
            changed = False
            for job in jobs.values():
                if job["status"] != STATUS_DELIVERED or job["reminded"] or not job["delivered_at"]:
                    continue
                if time.time() - job["delivered_at"] < s["reminder_hours"] * 3600:
                    continue

                try:
                    order = ctx.account.get_order(job["order_id"])
                except Exception:
                    ctx.logger.exception(f"Не удалось проверить заказ {job['order_id']} для напоминания")
                    continue

                if order.status == OrderStatuses.PAID:
                    try:
                        ctx.account.send_message(
                            job["chat_id"],
                            "👋 Напоминаем: Premium уже подарен — если всё пришло, не забудьте "
                            "подтвердить получение заказа на FunPay, это важно для продавца 🙏",
                        )
                    except Exception:
                        ctx.logger.exception(f"Не удалось отправить напоминание по заказу {job['order_id']}")
                job["reminded"] = True
                changed = True

            if changed:
                save_jobs(jobs)

    threading.Thread(target=reminder_worker, daemon=True).start()

    # ---------- Telegram меню ----------

    def build_status_text():
        s = get_settings()
        state = "включён ✅" if s["enabled"] else "выключен ⛔"
        configured = "настроен ✅" if is_configured(s) else "не настроен ⛔"
        jobs = get_jobs()
        queued = sum(1 for j in jobs.values() if j["status"] == STATUS_QUEUED)
        waiting = sum(1 for j in jobs.values() if j["status"] == STATUS_WAITING_USERNAME)
        tiers_text = ", ".join(
            f"{m}мес→лот {lid}" for m, lid in [(3, s["tier_lot_ids"]["3"]), (6, s["tier_lot_ids"]["6"]), (12, s["tier_lot_ids"]["12"])]
            if lid
        ) or "—"
        return (
            f"<b>Telegram Premium</b>: {state}, {configured}\n\n"
            f"Ключевое слово в лоте: {s['keyword']}\n"
            f"Наценка: {s['markup_percent']}%\n"
            f"Тарифы/лоты: {tiers_text}\n"
            f"Интервал обновления цены: {s['price_interval_hours']} ч.\n"
            f"Мин. баланс для продажи: {s['min_balance_ton']} TON ({'выкл' if s['min_balance_ton'] <= 0 else 'вкл'})\n"
            f"Напоминание о подтверждении: {s['reminder_hours']} ч. ({'выкл' if s['reminder_hours'] <= 0 else 'вкл'})\n\n"
            f"В очереди на выдачу: {queued}\n"
            f"Ждут username от покупателя: {waiting}"
        )

    @ctx.telegram.menu_item(SECTION, "📊 Статус", "tgpremium:status")
    def cbq_status(call):
        ctx.telegram.bot.send_message(call.message.chat.id, build_status_text())

    @ctx.telegram.menu_item(SECTION, "⚙️ Настроить доступ", "tgpremium:setup_ask")
    def cbq_setup_ask(call):
        ctx.telegram.bot.send_message(
            call.message.chat.id,
            "⚠️ Понадобится seed-фраза TON-кошелька. Заведите под это ОТДЕЛЬНЫЙ кошелёк с небольшим "
            "балансом — не основной. Если уже настраивали плагин Telegram Stars, можно использовать тот "
            "же кошелёк — просто введите те же данные ещё раз (плагины хранят настройки независимо друг от друга).",
        )

        def on_seed(msg):
            seed = msg.text.strip()

            def on_api_key(msg2):
                api_key = msg2.text.strip()

                def ask_cookies():
                    def on_cookies(msg3):
                        cookies = {}
                        for part in msg3.text.split(";"):
                            if "=" not in part:
                                continue
                            k, v = part.split("=", 1)
                            cookies[k.strip()] = v.strip()
                        missing = [k for k in REQUIRED_COOKIES if k not in cookies]
                        if missing:
                            ctx.telegram.bot.send_message(msg3.chat.id, f"Не хватает: {', '.join(missing)}. Попробуйте снова.")
                            ask_cookies()
                            return

                        def on_keyword(msg4):
                            s = get_settings()
                            s["seed_enc"] = crypto.encrypt(seed)
                            s["api_key"] = api_key
                            s["cookies"] = cookies
                            s["keyword"] = msg4.text.strip() or "premium"
                            save_settings(s)
                            ctx.telegram.bot.send_message(
                                msg4.chat.id,
                                "✅ Доступ настроен. Задайте лоты и наценку кнопкой «💲 Цена и лоты», "
                                "затем включите модуль кнопкой «▶️ Включить».",
                            )

                        ctx.telegram.ask(msg3.chat.id, msg3.from_user.id,
                                          "Ключевое слово в названии лота (по умолчанию 'premium')?", on_keyword)

                    ctx.telegram.ask(
                        call.message.chat.id, call.from_user.id,
                        "Cookies одной строкой в формате key=value; key=value — нужны "
                        f"{', '.join(REQUIRED_COOKIES)} (смотрите в DevTools браузера на fragment.com).",
                        on_cookies,
                    )

                ask_cookies()

            ctx.telegram.ask(msg.chat.id, msg.from_user.id, "Tonconsole API key (tonconsole.com)?", on_api_key)

        ctx.telegram.ask(call.message.chat.id, call.from_user.id, "Seed-фраза TON-кошелька (через пробел)?", on_seed)

    @ctx.telegram.menu_item(SECTION, "💲 Цена и лоты", "tgpremium:pricing_ask")
    def cbq_pricing_ask(call):
        def parse_lot_id(text):
            text = text.strip()
            if not text or text == "-":
                return None
            if not text.isdigit():
                raise ValueError
            return int(text)

        def on_lot3(msg):
            try:
                lot3 = parse_lot_id(msg.text)
            except ValueError:
                ctx.telegram.bot.send_message(msg.chat.id, "Нужно число (или '-', если этого тарифа нет).")
                return

            def on_lot6(msg2):
                try:
                    lot6 = parse_lot_id(msg2.text)
                except ValueError:
                    ctx.telegram.bot.send_message(msg2.chat.id, "Нужно число (или '-').")
                    return

                def on_lot12(msg3):
                    try:
                        lot12 = parse_lot_id(msg3.text)
                    except ValueError:
                        ctx.telegram.bot.send_message(msg3.chat.id, "Нужно число (или '-').")
                        return

                    def on_markup(msg4):
                        try:
                            markup = float(msg4.text.strip().replace(",", "."))
                        except ValueError:
                            ctx.telegram.bot.send_message(msg4.chat.id, "Наценка должна быть числом (в процентах).")
                            return

                        def on_interval(msg5):
                            try:
                                interval = float(msg5.text.strip().replace(",", "."))
                            except ValueError:
                                ctx.telegram.bot.send_message(msg5.chat.id, "Интервал должен быть числом (часы).")
                                return

                            def on_min_balance(msg6):
                                try:
                                    min_balance = float(msg6.text.strip().replace(",", "."))
                                except ValueError:
                                    ctx.telegram.bot.send_message(msg6.chat.id, "Нужно число (TON, 0 — выключить проверку).")
                                    return

                                def on_reminder(msg7):
                                    try:
                                        reminder = float(msg7.text.strip().replace(",", "."))
                                    except ValueError:
                                        ctx.telegram.bot.send_message(msg7.chat.id, "Нужно число (часы, 0 — выключить напоминание).")
                                        return
                                    s = get_settings()
                                    s["tier_lot_ids"] = {"3": lot3, "6": lot6, "12": lot12}
                                    s["markup_percent"] = markup
                                    s["price_interval_hours"] = interval
                                    s["min_balance_ton"] = min_balance
                                    s["reminder_hours"] = reminder
                                    s["last_price_update"] = 0
                                    save_settings(s)
                                    ctx.telegram.bot.send_message(msg7.chat.id, "✅ Настройки цены и лотов сохранены.")

                                ctx.telegram.ask(
                                    msg6.chat.id, msg6.from_user.id,
                                    "Через сколько часов напоминать покупателю подтвердить заказ (0 — не напоминать)?",
                                    on_reminder,
                                )

                            ctx.telegram.ask(
                                msg5.chat.id, msg5.from_user.id,
                                "Минимальный баланс кошелька в TON, ниже которого лоты снимаются с продажи (0 — не проверять)?",
                                on_min_balance,
                            )

                        ctx.telegram.ask(msg4.chat.id, msg4.from_user.id, "Как часто обновлять цену, в часах?", on_interval)

                    ctx.telegram.ask(msg3.chat.id, msg3.from_user.id, "Наценка сверх цены Fragment, в процентах?", on_markup)

                ctx.telegram.ask(msg2.chat.id, msg2.from_user.id, "ID лота для 12 месяцев? (число, или '-' если не продаёте)", on_lot12)

            ctx.telegram.ask(msg.chat.id, msg.from_user.id, "ID лота для 6 месяцев? (число, или '-' если не продаёте)", on_lot6)

        ctx.telegram.ask(
            call.message.chat.id, call.from_user.id,
            "ID лота для 3 месяцев? (число, или '-' если не продаёте)",
            on_lot3,
        )

    @ctx.telegram.menu_item(SECTION, "▶️ Включить", "tgpremium:on")
    def cbq_on(call):
        s = get_settings()
        if not is_configured(s):
            ctx.telegram.bot.send_message(call.message.chat.id, "Сначала настройте доступ кнопкой «⚙️ Настроить доступ».")
            return
        s["enabled"] = True
        save_settings(s)
        ctx.telegram.bot.send_message(call.message.chat.id, "✅ Включено.")

    @ctx.telegram.menu_item(SECTION, "⏸ Выключить", "tgpremium:off")
    def cbq_off(call):
        s = get_settings()
        s["enabled"] = False
        save_settings(s)
        ctx.telegram.bot.send_message(call.message.chat.id, "⛔ Выключено.")
