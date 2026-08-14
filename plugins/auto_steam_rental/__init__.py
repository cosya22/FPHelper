"""
Авто-аренда Steam-аккаунтов по заказам FunPay.

⚠️ ЭТО НАРУШАЕТ SUBSCRIBER AGREEMENT STEAM/VALVE — аккаунты там строго
персональные, шаринг/аренда за деньги запрещены договором. Valve реально
банит такие аккаунты, теряется вся библиотека игр на нём целиком. Это
осознанный риск владельца, плагин ничего от него не скрывает.

Флоу: покупатель оплачивает лот в категории (игре) X -> бот сразу
присылает логин/пароль аккаунта, привязанного к этой категории -> покупатель пишет !код,
когда Steam просит код Steam Guard, и получает актуальный код -> с этого
момента идёт отсчёт аренды -> по истечении бот пытается сам сменить
пароль через официальный визард восстановления (steam_password.py); если
не получилось — просит владельца сменить пароль вручную, аккаунт не
возвращается в пул, пока это не подтверждено.

Если покупатель ни разу не запросил код в течение grace-периода — заказ
автоматически возвращается, а аккаунт (пароль/данные которого уже видел
покупатель) тоже помечается "нужен ручной сброс" — на всякий случай.
"""

import threading
import time

from fphelper import PluginInfo
from FunPayAPI.common.enums import OrderStatuses

from . import crypto, steam_guard, steam_password

INFO = PluginInfo(
    name="Auto Steam Rental",
    version="1.5.0",
    description="Авто-аренда Steam-аккаунтов: выдача, коды Steam Guard, попытка авто-смены пароля по истечении.",
    author="you",
)

SECTION = "🎮 Steam-аренда"

STATUS_WAITING_START = "waiting_start"
STATUS_ACTIVE = "active"
STATUS_ENDED = "ended"
STATUS_REFUNDED = "refunded"

ACC_AVAILABLE = "available"
ACC_RENTED = "rented"
ACC_NEEDS_RESET = "needs_reset"

EXPIRE_CHECK_INTERVAL = 30
NOSHOW_CHECK_INTERVAL = 60
LOT_CHECK_INTERVAL = 120
REVIEW_CHECK_INTERVAL = 900


def setup(ctx):
    def get_settings():
        s = ctx.storage.get("settings", {})
        s.setdefault("keyword", "аренда")
        s.setdefault("duration_seconds_per_unit", 3600.0)
        s.setdefault("grace_period_minutes", 30.0)
        s.setdefault("review_bonus_minutes", 0.0)
        s.setdefault("lot_categories", {})  # {"lot_id": "категория" | "" (любая)}
        s.setdefault("enabled", False)
        return s

    def save_settings(s):
        ctx.storage.set("settings", s)

    def get_accounts():
        return ctx.storage.get("accounts", {})

    def save_accounts(accounts):
        ctx.storage.set("accounts", accounts)

    def get_jobs():
        return ctx.storage.get("jobs", {})

    def save_jobs(jobs):
        ctx.storage.set("jobs", jobs)

    def get_deactivated_lots():
        return set(ctx.storage.get("deactivated_lot_ids", []))

    def save_deactivated_lots(lot_ids):
        ctx.storage.set("deactivated_lot_ids", sorted(lot_ids))

    def load_mafile(account):
        return __import__("json").loads(crypto.decrypt(account["mafile_enc"]))

    def find_available_account(subcategory_name):
        accounts = get_accounts()
        needle = (subcategory_name or "").strip().lower()
        # сначала аккаунты, привязанные именно к этой категории лота
        for login, acc in accounts.items():
            if acc["status"] == ACC_AVAILABLE and acc.get("category", "").strip().lower() == needle and needle:
                return login, acc
        # затем — универсальные аккаунты без привязки к категории
        for login, acc in accounts.items():
            if acc["status"] == ACC_AVAILABLE and not acc.get("category", ""):
                return login, acc
        return None, None

    def has_available_for_category(category):
        needle = (category or "").strip().lower()
        for acc in get_accounts().values():
            if acc["status"] != ACC_AVAILABLE:
                continue
            acc_category = acc.get("category", "").strip().lower()
            if not acc_category or acc_category == needle:
                return True
        return False

    def find_lot_id_for_category(category):
        s = get_settings()
        needle = (category or "").strip().lower()
        # сначала лот именно этой категории
        for lot_id_str, cat in s["lot_categories"].items():
            if needle and cat.strip().lower() == needle:
                return lot_id_str
        # затем — лот без привязки к конкретной категории
        for lot_id_str, cat in s["lot_categories"].items():
            if not cat.strip():
                return lot_id_str
        return None

    # ---------- события FunPay: выдача ----------

    @ctx.events.new_order
    def on_order(event):
        order = event.order
        s = get_settings()
        if not s["enabled"]:
            return
        if s["keyword"].lower() not in order.description.lower():
            return

        category = getattr(order, "subcategory_name", "") or ""

        try:
            chat = ctx.account.get_chat_by_name(order.buyer_username, make_request=True)
            chat_id = chat.id if chat else order.buyer_username
        except Exception:
            chat_id = order.buyer_username

        duration_seconds = (order.amount or 1) * s["duration_seconds_per_unit"]

        # продление: у покупателя уже есть активная/ожидающая аренда в этой же категории —
        # добавляем время к ней, а не ищем новый аккаунт
        jobs = get_jobs()
        existing_job = next(
            (j for j in jobs.values()
             if j["buyer_username"] == order.buyer_username
             and j["status"] in (STATUS_WAITING_START, STATUS_ACTIVE)
             and j.get("category", "") == category),
            None,
        )
        if existing_job is not None:
            job = jobs[existing_job["order_id"]]
            if job["status"] == STATUS_ACTIVE and job["rental_ends_at"]:
                job["rental_ends_at"] += duration_seconds
                left = int((job["rental_ends_at"] - time.time()) // 3600)
                end_text = f"Осталось теперь: {left} ч."
            else:
                job["duration_seconds"] += duration_seconds
                end_text = "Прибавится к длительности, когда аренда начнётся (после первого !код)."
            save_jobs(jobs)
            try:
                ctx.account.send_message(
                    chat_id,
                    f"➕ Аренда продлена на {int(duration_seconds // 3600)} ч.! {end_text}",
                )
            except Exception:
                ctx.logger.exception(f"Не удалось уведомить о продлении по заказу {order.id}")
            return

        login, account = find_available_account(category)

        if account is None:
            try:
                ctx.account.refund(order.id)
            except Exception:
                ctx.logger.exception(f"Не удалось оформить авто-возврат по заказу {order.id}")
            ctx.notify_owner(
                f"⚠️ Заказ {order.id}: нет свободных аккаунтов" + (f" для категории «{category}»" if category else "") +
                " — оформлен автовозврат."
            )
            return

        accounts = get_accounts()
        accounts[login]["status"] = ACC_RENTED
        accounts[login]["current_order_id"] = order.id
        save_accounts(accounts)

        jobs[order.id] = {
            "order_id": order.id,
            "buyer_username": order.buyer_username,
            "chat_id": chat_id,
            "login": login,
            "category": category,
            "duration_seconds": duration_seconds,
            "status": STATUS_WAITING_START,
            "rental_started_at": None,
            "rental_ends_at": None,
            "created_at": time.time(),
            "review_bonus_applied": False,
        }
        save_jobs(jobs)

        password = crypto.decrypt(account["password_enc"])
        try:
            ctx.account.send_message(
                chat_id,
                f"🎮 Спасибо за заказ! Данные для входа:\n\n"
                f"👤 Логин: {login}\n"
                f"🔑 Пароль: {password}\n\n"
                f"🛡️ Когда Steam попросит код Steam Guard — напишите сюда !код, и я пришлю актуальный.\n"
                f"⏱️ Отсчёт аренды ({int(duration_seconds // 3600)} ч.) начнётся с первого запроса кода.\n\n"
                f"📋 Команды:\n"
                f"!код - получить код Steam Guard\n"
                f"!время - сколько времени осталось\n"
                f"!продление - как продлить аренду",
            )
        except Exception:
            ctx.logger.exception(f"Не удалось отправить данные аккаунта по заказу {order.id}")

    @ctx.events.new_message
    def on_message(event):
        message = event.message
        if message.author_id == ctx.account.id or not message.text:
            return
        text = message.text.strip().lower()
        if text not in ("!код", "!время", "!продление"):
            return

        jobs = get_jobs()
        job = next(
            (j for j in jobs.values() if j["buyer_username"] == message.author and j["status"] in (STATUS_WAITING_START, STATUS_ACTIVE)),
            None,
        )
        if job is None:
            return

        accounts = get_accounts()
        account = accounts.get(job["login"])
        if account is None:
            return

        if text == "!код":
            try:
                mafile = load_mafile(account)
                code = steam_guard.generate_code(mafile["shared_secret"])
            except Exception:
                ctx.logger.exception(f"Не удалось сгенерировать код Steam Guard для заказа {job['order_id']}")
                try:
                    ctx.account.send_message(message.chat_id, "❌ Не удалось получить код, напишите продавцу.")
                except Exception:
                    pass
                return

            if job["status"] == STATUS_WAITING_START:
                job["status"] = STATUS_ACTIVE
                job["rental_started_at"] = time.time()
                job["rental_ends_at"] = job["rental_started_at"] + job["duration_seconds"]
                save_jobs(jobs)

            try:
                ctx.account.send_message(message.chat_id, f"Код Steam Guard: {code}")
            except Exception:
                pass

        elif text == "!время":
            if job["status"] != STATUS_ACTIVE or not job["rental_ends_at"]:
                reply = "Аренда ещё не началась — запросите код командой !код."
            else:
                left = max(0, int(job["rental_ends_at"] - time.time()))
                reply = f"Осталось: {left // 3600} ч. {(left % 3600) // 60} мин."
            try:
                ctx.account.send_message(message.chat_id, reply)
            except Exception:
                pass

        else:  # !продление
            if job["status"] == STATUS_ACTIVE and job["rental_ends_at"]:
                left = max(0, int(job["rental_ends_at"] - time.time()))
                left_text = f"{left // 3600}ч {(left % 3600) // 60}м"
            else:
                left_text = "аренда ещё не началась (запросите !код)"

            lot_id = find_lot_id_for_category(job.get("category", ""))
            if lot_id:
                reply = (
                    f"🔄 Для продления аренды оплатите лот по ссылке:\n"
                    f"https://funpay.com/lots/offer?id={lot_id}\n\n"
                    f"∟ Осталось: {left_text}"
                )
            else:
                reply = (
                    f"🔄 Чтобы продлить аренду, оформите новый заказ на любой лот этой же игры — "
                    f"я сам добавлю время к текущей аренде.\n\n"
                    f"∟ Осталось: {left_text}"
                )
            try:
                ctx.account.send_message(message.chat_id, reply)
            except Exception:
                pass

    # ---------- воркер: истечение аренды ----------

    def apply_password_reset(login, account, jobs, job):
        try:
            mafile = load_mafile(account)
            steamid = int((mafile.get("Session") or {}).get("SteamID", 0))
            new_password = steam_password.change_password_sync(
                login=login,
                current_password=crypto.decrypt(account["password_enc"]),
                shared_secret=mafile["shared_secret"],
                identity_secret=mafile["identity_secret"],
                device_id=mafile.get("device_id", ""),
                steamid=steamid,
            )
            accounts = get_accounts()
            accounts[login]["password_enc"] = crypto.encrypt(new_password)
            accounts[login]["status"] = ACC_AVAILABLE
            accounts[login]["current_order_id"] = None
            save_accounts(accounts)
            ctx.notify_owner(f"✅ Аренда {login} завершена, пароль сменён автоматически. Аккаунт снова доступен.")
        except Exception as e:
            ctx.logger.exception(f"Не удалось автоматически сменить пароль {login}")
            accounts = get_accounts()
            accounts[login]["status"] = ACC_NEEDS_RESET
            accounts[login]["current_order_id"] = None
            save_accounts(accounts)
            ctx.notify_owner(
                f"⚠️ Аренда {login} завершена, но автосмена пароля не удалась ({e}). "
                f"Смените пароль вручную и нажмите «🔄 Пароль сброшен» в меню — до этого аккаунт не сдаётся снова."
            )

        job["status"] = STATUS_ENDED
        save_jobs(jobs)
        try:
            ctx.account.send_message(job["chat_id"], "⏰ Время аренды истекло, спасибо за использование!")
        except Exception:
            pass

    def expire_worker():
        while True:
            time.sleep(EXPIRE_CHECK_INTERVAL)
            jobs = get_jobs()
            accounts = get_accounts()
            for job in list(jobs.values()):
                if job["status"] != STATUS_ACTIVE or not job["rental_ends_at"]:
                    continue
                if time.time() < job["rental_ends_at"]:
                    continue
                account = accounts.get(job["login"])
                if account is None:
                    job["status"] = STATUS_ENDED
                    save_jobs(jobs)
                    continue
                apply_password_reset(job["login"], account, jobs, job)

    threading.Thread(target=expire_worker, daemon=True).start()

    # ---------- воркер: неявка (не запросил код вовремя) ----------

    def noshow_worker():
        while True:
            time.sleep(NOSHOW_CHECK_INTERVAL)
            s = get_settings()
            jobs = get_jobs()
            accounts = get_accounts()
            changed_jobs = False
            changed_accounts = False
            for job in list(jobs.values()):
                if job["status"] != STATUS_WAITING_START:
                    continue
                if time.time() - job["created_at"] < s["grace_period_minutes"] * 60:
                    continue
                try:
                    ctx.account.refund(job["order_id"])
                except Exception:
                    ctx.logger.exception(f"Не удалось авто-вернуть заказ {job['order_id']}")
                job["status"] = STATUS_REFUNDED
                changed_jobs = True
                account = accounts.get(job["login"])
                if account is not None:
                    # покупатель уже видел пароль — аккаунт нужно сбросить вручную на всякий случай
                    account["status"] = ACC_NEEDS_RESET
                    account["current_order_id"] = None
                    changed_accounts = True
                ctx.notify_owner(
                    f"↩️ Заказ {job['order_id']}: покупатель не запросил код за {s['grace_period_minutes']} мин. "
                    f"Оформлен возврат. Аккаунт {job['login']} требует ручного сброса пароля перед следующей сдачей."
                )
                try:
                    ctx.account.send_message(job["chat_id"], "Заказ автоматически возвращён — вы не подтвердили вход вовремя.")
                except Exception:
                    pass
            if changed_jobs:
                save_jobs(jobs)
            if changed_accounts:
                save_accounts(accounts)

    threading.Thread(target=noshow_worker, daemon=True).start()

    # ---------- воркер: авто-вкл/выкл лотов по наличию свободных аккаунтов ----------

    def set_lot_active(lot_id, active):
        fields = ctx.account.get_lot_fields(lot_id)
        fields.active = active
        fields.renew_fields()
        ctx.account.save_lot(fields)

    def lot_availability_worker():
        while True:
            time.sleep(LOT_CHECK_INTERVAL)
            s = get_settings()
            if not s["enabled"] or not s["lot_categories"]:
                continue
            deactivated = get_deactivated_lots()
            changed = False
            for lot_id_str, category in s["lot_categories"].items():
                lot_id = int(lot_id_str)
                label = f"«{category}»" if category else "без привязки к игре"
                try:
                    if not has_available_for_category(category):
                        if lot_id not in deactivated:
                            set_lot_active(lot_id, False)
                            deactivated.add(lot_id)
                            changed = True
                            ctx.notify_owner(f"⏸ Лот {lot_id} ({label}) снят с продажи: нет свободных аккаунтов под эту игру.")
                    else:
                        if lot_id in deactivated:
                            set_lot_active(lot_id, True)
                            deactivated.discard(lot_id)
                            changed = True
                            ctx.notify_owner(f"▶️ Лот {lot_id} ({label}) снова в продаже: появился свободный аккаунт.")
                except Exception:
                    ctx.logger.exception(f"Не удалось обновить состояние лота {lot_id}")
            if changed:
                save_deactivated_lots(deactivated)

    threading.Thread(target=lot_availability_worker, daemon=True).start()

    # ---------- воркер: бонус за отзыв ----------

    def review_bonus_worker():
        while True:
            time.sleep(REVIEW_CHECK_INTERVAL)
            s = get_settings()
            if s["review_bonus_minutes"] <= 0:
                continue
            jobs = get_jobs()
            changed = False
            for job in jobs.values():
                if job["status"] != STATUS_ACTIVE or job["review_bonus_applied"]:
                    continue
                try:
                    order = ctx.account.get_order(job["order_id"])
                except Exception:
                    continue
                if order.review and order.review.stars == 5:
                    job["rental_ends_at"] += s["review_bonus_minutes"] * 60
                    job["review_bonus_applied"] = True
                    changed = True
                    try:
                        ctx.account.send_message(
                            job["chat_id"],
                            f"⭐ Спасибо за отзыв! Добавили {int(s['review_bonus_minutes'])} мин. к аренде.",
                        )
                    except Exception:
                        pass
            if changed:
                save_jobs(jobs)

    threading.Thread(target=review_bonus_worker, daemon=True).start()

    # ---------- Telegram меню ----------

    def build_status_text():
        s = get_settings()
        state = "включён ✅" if s["enabled"] else "выключен ⛔"
        accounts = get_accounts()
        avail = sum(1 for a in accounts.values() if a["status"] == ACC_AVAILABLE)
        rented = sum(1 for a in accounts.values() if a["status"] == ACC_RENTED)
        needs_reset = sum(1 for a in accounts.values() if a["status"] == ACC_NEEDS_RESET)
        lots_parts = []
        for lid, cat in s["lot_categories"].items():
            lots_parts.append(f"{lid} ({cat if cat else 'любая'})")
        lots_text = ", ".join(lots_parts) or "—"
        return (
            f"<b>Steam-аренда</b>: {state}\n\n"
            f"Ключевое слово: {s['keyword']}\n"
            f"Длительность: {s['duration_seconds_per_unit'] / 3600:.1f} ч. за единицу\n"
            f"Grace-период: {s['grace_period_minutes']} мин.\n"
            f"Бонус за отзыв: {s['review_bonus_minutes']} мин.\n"
            f"Лоты для авто-вкл/выкл: {lots_text}\n\n"
            f"Аккаунтов: {len(accounts)} (свободно {avail}, в аренде {rented}, нужен сброс {needs_reset})"
        )

    @ctx.telegram.menu_item(SECTION, "📊 Статус", "steamrent:status")
    def cbq_status(call):
        ctx.telegram.bot.send_message(call.message.chat.id, build_status_text())

    @ctx.telegram.menu_item(SECTION, "📋 Аккаунты", "steamrent:accounts")
    def cbq_accounts(call):
        accounts = get_accounts()
        if not accounts:
            ctx.telegram.bot.send_message(call.message.chat.id, "Аккаунтов пока нет.")
            return
        lines = ["<b>Аккаунты:</b>\n"]
        icons = {ACC_AVAILABLE: "🟢", ACC_RENTED: "🔵", ACC_NEEDS_RESET: "🔴"}
        for login, a in accounts.items():
            category = f" [{a['category']}]" if a.get("category") else " [любая категория]"
            lines.append(f"{icons.get(a['status'], '❔')} <code>{login}</code>{category} — {a['status']}")
        ctx.telegram.bot.send_message(call.message.chat.id, "\n".join(lines))

    @ctx.telegram.menu_item(SECTION, "➕ Добавить аккаунт", "steamrent:add_ask")
    def cbq_add_ask(call):
        def on_login(msg):
            login = msg.text.strip()

            def on_password(msg2):
                password = msg2.text.strip()

                def on_category(msg3):
                    category = msg3.text.strip()
                    if category == "-":
                        category = ""

                    def on_mafile(msg4):
                        document = getattr(msg4, "document", None)
                        if not document:
                            ctx.telegram.bot.send_message(msg4.chat.id, "Нужен файл .maFile. Попробуйте снова.")
                            on_mafile_ask()
                            return
                        try:
                            file_info = ctx.telegram.bot.get_file(document.file_id)
                            raw = ctx.telegram.bot.download_file(file_info.file_path)
                            mafile = __import__("json").loads(raw.decode("utf-8"))
                        except Exception as e:
                            ctx.telegram.bot.send_message(msg4.chat.id, f"❌ Не удалось прочитать maFile: {e}")
                            return
                        missing = [f for f in ("shared_secret", "identity_secret") if not mafile.get(f)]
                        if missing:
                            ctx.telegram.bot.send_message(msg4.chat.id, f"В maFile не хватает: {', '.join(missing)}.")
                            return

                        accounts = get_accounts()
                        accounts[login] = {
                            "login": login,
                            "category": category,
                            "password_enc": crypto.encrypt(password),
                            "mafile_enc": crypto.encrypt(__import__("json").dumps(mafile)),
                            "status": ACC_AVAILABLE,
                            "current_order_id": None,
                        }
                        save_accounts(accounts)
                        ctx.telegram.bot.send_message(msg4.chat.id, f"✅ Аккаунт {login} добавлен.")

                    def on_mafile_ask():
                        ctx.telegram.ask(msg3.chat.id, msg3.from_user.id, "Пришлите файл .maFile (документом).", on_mafile)

                    on_mafile_ask()

                ctx.telegram.ask(
                    msg2.chat.id, msg2.from_user.id,
                    "Название категории лота на FunPay для этого аккаунта — точно как оно указано на "
                    "странице лота (например: 'PUBG: BATTLEGROUNDS — аккаунты'), или '-' если аккаунт "
                    "подходит под любую категорию (запасной пул)?",
                    on_category,
                )

            ctx.telegram.ask(msg.chat.id, msg.from_user.id, "Текущий пароль аккаунта?", on_password)

        ctx.telegram.ask(call.message.chat.id, call.from_user.id, "Логин аккаунта Steam?", on_login)

    @ctx.telegram.menu_item(SECTION, "🔄 Пароль сброшен", "steamrent:reset_ask")
    def cbq_reset_ask(call):
        def on_login(msg):
            login = msg.text.strip()
            accounts = get_accounts()
            if login not in accounts:
                ctx.telegram.bot.send_message(msg.chat.id, "Такого аккаунта нет.")
                return

            def on_new_password(msg2):
                accounts2 = get_accounts()
                accounts2[login]["password_enc"] = crypto.encrypt(msg2.text.strip())
                accounts2[login]["status"] = ACC_AVAILABLE
                save_accounts(accounts2)
                ctx.telegram.bot.send_message(msg2.chat.id, f"✅ {login} снова доступен для аренды.")

            ctx.telegram.ask(msg.chat.id, msg.from_user.id, "Пришлите новый пароль, который вы установили вручную.", on_new_password)

        ctx.telegram.ask(call.message.chat.id, call.from_user.id, "Логин аккаунта, для которого пароль сброшен вручную?", on_login)

    @ctx.telegram.menu_item(SECTION, "🗑 Удалить аккаунт", "steamrent:remove_ask")
    def cbq_remove_ask(call):
        def on_login(msg):
            login = msg.text.strip()
            accounts = get_accounts()
            if login not in accounts:
                ctx.telegram.bot.send_message(msg.chat.id, "Такого аккаунта нет.")
                return
            del accounts[login]
            save_accounts(accounts)
            ctx.telegram.bot.send_message(msg.chat.id, f"✅ {login} удалён.")

        ctx.telegram.ask(call.message.chat.id, call.from_user.id, "Логин аккаунта для удаления?", on_login)

    @ctx.telegram.menu_item(SECTION, "⚙️ Настроить", "steamrent:setup_ask")
    def cbq_setup_ask(call):
        def on_keyword(msg):
            keyword = msg.text.strip() or "аренда"

            def on_hours(msg2):
                try:
                    hours = float(msg2.text.strip().replace(",", "."))
                except ValueError:
                    ctx.telegram.bot.send_message(msg2.chat.id, "Нужно число (часы за 1 единицу лота).")
                    return

                def on_grace(msg3):
                    try:
                        grace = float(msg3.text.strip().replace(",", "."))
                    except ValueError:
                        ctx.telegram.bot.send_message(msg3.chat.id, "Нужно число (минуты).")
                        return

                    def on_bonus(msg4):
                        try:
                            bonus = float(msg4.text.strip().replace(",", "."))
                        except ValueError:
                            ctx.telegram.bot.send_message(msg4.chat.id, "Нужно число (минуты, 0 — выключить).")
                            return

                        def on_lots(msg5):
                            text = msg5.text.strip()
                            lot_categories = {}
                            if text != "-":
                                for line in text.splitlines():
                                    line = line.strip()
                                    if not line:
                                        continue
                                    if ":" not in line:
                                        ctx.telegram.bot.send_message(
                                            msg5.chat.id, f"Строка «{line}» не в формате ID_лота:категория, пропущена."
                                        )
                                        continue
                                    lot_id_part, category_part = line.split(":", 1)
                                    lot_id_part = lot_id_part.strip()
                                    if not lot_id_part.isdigit():
                                        ctx.telegram.bot.send_message(
                                            msg5.chat.id, f"«{lot_id_part}» не похоже на ID лота, строка пропущена."
                                        )
                                        continue
                                    category = category_part.strip()
                                    if category == "-":
                                        category = ""
                                    lot_categories[lot_id_part] = category
                            s = get_settings()
                            s["keyword"] = keyword
                            s["duration_seconds_per_unit"] = hours * 3600
                            s["grace_period_minutes"] = grace
                            s["review_bonus_minutes"] = bonus
                            s["lot_categories"] = lot_categories
                            save_settings(s)
                            ctx.telegram.bot.send_message(msg5.chat.id, "✅ Настройки сохранены.")

                        ctx.telegram.ask(
                            msg4.chat.id, msg4.from_user.id,
                            "Лоты для авто-вкл/выкл по наличию аккаунтов. Каждый лот на новой строке в формате "
                            "ID_лота:категория (категория — как у аккаунта, или '-' для лота без привязки к "
                            "конкретной игре). Например:\n123456:PUBG: BATTLEGROUNDS — аккаунты\n789012:-\n"
                            "Пришлите '-', если авто-вкл/выкл не нужен.",
                            on_lots,
                        )

                    ctx.telegram.ask(msg3.chat.id, msg3.from_user.id, "Бонус за отзыв 5⭐, в минутах (0 — выключить)?", on_bonus)

                ctx.telegram.ask(msg2.chat.id, msg2.from_user.id, "Grace-период до авто-возврата, в минутах?", on_grace)

            ctx.telegram.ask(msg.chat.id, msg.from_user.id, "Сколько часов аренды за 1 единицу количества в лоте?", on_hours)

        ctx.telegram.ask(call.message.chat.id, call.from_user.id, "Ключевое слово в названии лота (по умолчанию 'аренда')?", on_keyword)

    @ctx.telegram.menu_item(SECTION, "▶️ Включить", "steamrent:on")
    def cbq_on(call):
        s = get_settings()
        s["enabled"] = True
        save_settings(s)
        ctx.telegram.bot.send_message(call.message.chat.id, "✅ Включено.")

    @ctx.telegram.menu_item(SECTION, "⏸ Выключить", "steamrent:off")
    def cbq_off(call):
        s = get_settings()
        s["enabled"] = False
        save_settings(s)
        ctx.telegram.bot.send_message(call.message.chat.id, "⛔ Выключено.")
