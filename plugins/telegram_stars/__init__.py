"""
Авто-выдача Telegram Stars по заказам FunPay через Fragment.com.

Официальный Bot API не умеет пополнять чужой баланс Stars — это делается только
через Fragment (покупка за TON, доставка на username), и делается неофициально:
используется сторонняя библиотека pyfragment (не от Telegram). Из-за этого нужен
TON-кошелёк с seed-фразой — ЗАВЕДИТЕ ПОД ЭТО ОТДЕЛЬНЫЙ КОШЕЛЁК с небольшим балансом,
не используйте основной. Seed хранится на диске в зашифрованном виде (crypto.py),
но раз к нему обращается сторонняя библиотека — риск выше, чем у обычного пароля.

Флоу: покупатель оплачивает лот на FunPay -> бот просит его Telegram username в
чате -> username пойман по регулярке -> заказ встаёт в очередь -> воркер звонит в
Fragment и покупает Stars -> покупателю приходит подтверждение в чат FunPay.
"""

import re
import threading
import time

from fphelper import PluginInfo
from pyfragment.exceptions import FragmentError, UserNotFoundError

from . import crypto, fragment_client

INFO = PluginInfo(
    name="Telegram Stars",
    version="1.0.0",
    description="Авто-выдача Telegram Stars через Fragment по заказам FunPay.",
    author="you",
)

SECTION = "⭐ Telegram Stars"
USERNAME_RE = re.compile(r"@([a-zA-Z][a-zA-Z0-9_]{4,31})")

STATUS_WAITING_USERNAME = "waiting_username"
STATUS_QUEUED = "queued"
STATUS_DELIVERED = "delivered"
STATUS_FAILED = "failed"

MAX_ATTEMPTS = 3
CHECK_INTERVAL = 5
REQUIRED_COOKIES = ("stel_ssid", "stel_dt", "stel_token", "stel_ton_token")


def setup(ctx):
    def get_settings():
        s = ctx.storage.get("settings", {})
        s.setdefault("keyword", "stars")
        s.setdefault("enabled", False)
        s.setdefault("seed_enc", None)
        s.setdefault("api_key", None)
        s.setdefault("cookies", None)
        return s

    def save_settings(s):
        ctx.storage.set("settings", s)

    def is_configured(s):
        return bool(s["seed_enc"] and s["api_key"] and s["cookies"])

    def get_jobs():
        return ctx.storage.get("jobs", {})

    def save_jobs(jobs):
        ctx.storage.set("jobs", jobs)

    # ---------- события FunPay ----------

    @ctx.events.new_order
    def on_order(event):
        order = event.order
        s = get_settings()
        if not s["enabled"] or not is_configured(s):
            return
        if s["keyword"].lower() not in order.description.lower():
            return

        try:
            chat = ctx.account.get_chat_by_name(order.buyer_username, make_request=True)
            chat_id = chat.id if chat else order.buyer_username
        except Exception:
            chat_id = order.buyer_username

        amount = order.amount or 1
        jobs = get_jobs()
        jobs[order.id] = {
            "order_id": order.id,
            "buyer_username": order.buyer_username,
            "chat_id": chat_id,
            "amount": amount,
            "telegram_username": None,
            "status": STATUS_WAITING_USERNAME,
            "attempts": 0,
            "error": None,
        }
        save_jobs(jobs)

        try:
            ctx.account.send_message(
                chat_id,
                f"Спасибо за заказ! Пришлите сюда ваш Telegram username (например, @username) — "
                f"на него начислим {amount} Stars.",
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
            ctx.account.send_message(message.chat_id, "Принято! Stars придут в течение нескольких минут.")
        except Exception:
            pass

    # ---------- фоновый воркер ----------

    def worker():
        while True:
            time.sleep(CHECK_INTERVAL)
            s = get_settings()
            if not s["enabled"] or not is_configured(s):
                continue

            jobs = get_jobs()
            job = next((j for j in jobs.values() if j["status"] == STATUS_QUEUED), None)
            if job is None:
                continue

            try:
                seed = crypto.decrypt(s["seed_enc"])
                fragment_client.purchase_stars_sync(
                    seed, s["api_key"], s["cookies"], f"@{job['telegram_username']}", job["amount"]
                )
                job["status"] = STATUS_DELIVERED
                save_jobs(jobs)
                try:
                    ctx.account.send_message(job["chat_id"], f"✅ Начислено {job['amount']} Stars. Спасибо за покупку!")
                except Exception:
                    pass
                ctx.notify_admins(
                    f"✅ Заказ {job['order_id']}: выдано {job['amount']} Stars на @{job['telegram_username']}"
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
            except FragmentError as e:
                job["attempts"] += 1
                if job["attempts"] >= MAX_ATTEMPTS:
                    job["status"] = STATUS_FAILED
                    job["error"] = str(e)
                    ctx.notify_admins(f"❌ Заказ {job['order_id']}: не удалось выдать Stars — {e}")
                save_jobs(jobs)
            except Exception:
                ctx.logger.exception(f"Неожиданная ошибка при выдаче заказа {job['order_id']}")
                job["attempts"] += 1
                if job["attempts"] >= MAX_ATTEMPTS:
                    job["status"] = STATUS_FAILED
                save_jobs(jobs)

    threading.Thread(target=worker, daemon=True).start()

    # ---------- Telegram меню ----------

    def build_status_text():
        s = get_settings()
        state = "включён ✅" if s["enabled"] else "выключен ⛔"
        configured = "настроен ✅" if is_configured(s) else "не настроен ⛔"
        jobs = get_jobs()
        queued = sum(1 for j in jobs.values() if j["status"] == STATUS_QUEUED)
        waiting = sum(1 for j in jobs.values() if j["status"] == STATUS_WAITING_USERNAME)
        return (
            f"<b>Telegram Stars</b>: {state}, {configured}\n\n"
            f"Ключевое слово в лоте: {s['keyword']}\n"
            f"В очереди на выдачу: {queued}\n"
            f"Ждут username от покупателя: {waiting}"
        )

    @ctx.telegram.menu_item(SECTION, "📊 Статус", "tgstars:status")
    def cbq_status(call):
        ctx.telegram.bot.send_message(call.message.chat.id, build_status_text())

    @ctx.telegram.menu_item(SECTION, "⚙️ Настроить", "tgstars:setup_ask")
    def cbq_setup_ask(call):
        ctx.telegram.bot.send_message(
            call.message.chat.id,
            "⚠️ Понадобится seed-фраза TON-кошелька. Заведите под это ОТДЕЛЬНЫЙ кошелёк с небольшим "
            "балансом — не основной. Seed шифруется перед сохранением на диск, но им пользуется "
            "сторонняя библиотека (pyfragment, не от Telegram), так что риск выше, чем у обычного пароля.",
        )

        def ask_seed():
            def on_seed(msg):
                seed = msg.text.strip()
                ask_api_key(seed)

            ctx.telegram.ask(call.message.chat.id, call.from_user.id, "Seed-фраза TON-кошелька (слова через пробел)?", on_seed)

        def ask_api_key(seed):
            def on_api_key(msg):
                ask_cookies(seed, msg.text.strip())

            ctx.telegram.ask(call.message.chat.id, call.from_user.id, "Tonconsole API key (получить на tonconsole.com)?", on_api_key)

        def ask_cookies(seed, api_key):
            def on_cookies(msg):
                cookies = {}
                for part in msg.text.split(";"):
                    if "=" not in part:
                        continue
                    k, v = part.split("=", 1)
                    cookies[k.strip()] = v.strip()
                missing = [k for k in REQUIRED_COOKIES if k not in cookies]
                if missing:
                    ctx.telegram.bot.send_message(msg.chat.id, f"Не хватает: {', '.join(missing)}. Попробуйте снова.")
                    ask_cookies(seed, api_key)
                    return
                ask_keyword(seed, api_key, cookies)

            ctx.telegram.ask(
                call.message.chat.id, call.from_user.id,
                "Cookies одной строкой в формате key=value; key=value — нужны "
                f"{', '.join(REQUIRED_COOKIES)} (смотрите в DevTools браузера на fragment.com).",
                on_cookies,
            )

        def ask_keyword(seed, api_key, cookies):
            def on_keyword(msg):
                s = get_settings()
                s["seed_enc"] = crypto.encrypt(seed)
                s["api_key"] = api_key
                s["cookies"] = cookies
                s["keyword"] = msg.text.strip() or "stars"
                save_settings(s)
                ctx.telegram.bot.send_message(
                    msg.chat.id, "✅ Настроено. Включите модуль кнопкой «▶️ Включить», когда будете готовы."
                )

            ctx.telegram.ask(
                call.message.chat.id, call.from_user.id,
                "Ключевое слово в названии лота, по которому ловить заказы (например 'stars')?",
                on_keyword,
            )

        ask_seed()

    @ctx.telegram.menu_item(SECTION, "▶️ Включить", "tgstars:on")
    def cbq_on(call):
        s = get_settings()
        if not is_configured(s):
            ctx.telegram.bot.send_message(call.message.chat.id, "Сначала настройте кнопкой «⚙️ Настроить».")
            return
        s["enabled"] = True
        save_settings(s)
        ctx.telegram.bot.send_message(call.message.chat.id, "✅ Включено.")

    @ctx.telegram.menu_item(SECTION, "⏸ Выключить", "tgstars:off")
    def cbq_off(call):
        s = get_settings()
        s["enabled"] = False
        save_settings(s)
        ctx.telegram.bot.send_message(call.message.chat.id, "⛔ Выключено.")
