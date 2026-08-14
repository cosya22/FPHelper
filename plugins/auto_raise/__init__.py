"""
Авто-поднятие лотов: раз в интервал поднимает выбранные категории через
account.raise_lots(). FunPay сам ограничивает частоту поднятия одной категории
(обычно ~4 часа) — при попытке поднять раньше срока FunPayAPI кидает RaiseError
с полем wait_time, и мы используем его, чтобы не долбить сайт лишними запросами.
"""

import threading
import time

from fphelper import PluginInfo
from FunPayAPI.common.exceptions import RaiseError

INFO = PluginInfo(
    name="Auto Raise Lots",
    version="1.0.0",
    description="Периодически поднимает выбранные категории лотов на FunPay.",
    author="you",
)

CHECK_INTERVAL = 60  # как часто проверяем, не пора ли поднять очередную категорию
DEFAULT_RETRY_AFTER = 4 * 60 * 60  # если FunPay не прислал wait_time, ждём 4 часа


def setup(ctx):
    def get_state():
        return ctx.storage.all() or {"enabled": True, "category_ids": [], "next_attempt": {}}

    def save_state(state):
        ctx.storage.update(state)

    state = get_state()
    state.setdefault("enabled", True)
    state.setdefault("category_ids", [])
    state.setdefault("next_attempt", {})
    save_state(state)

    def worker():
        while True:
            time.sleep(CHECK_INTERVAL)
            state = get_state()
            if not state.get("enabled"):
                continue

            now = time.time()
            changed = False
            for category_id in state.get("category_ids", []):
                key = str(category_id)
                next_at = state["next_attempt"].get(key, 0)
                if now < next_at:
                    continue

                try:
                    ctx.account.raise_lots(int(category_id))
                    state["next_attempt"][key] = now + DEFAULT_RETRY_AFTER
                    ctx.logger.info(f"Категория {category_id} поднята")
                    changed = True
                except RaiseError as e:
                    wait = e.wait_time or DEFAULT_RETRY_AFTER
                    state["next_attempt"][key] = now + wait
                    changed = True
                    ctx.logger.info(f"Категория {category_id}: рано поднимать, повтор через {wait} сек")
                except Exception:
                    state["next_attempt"][key] = now + 300
                    changed = True
                    ctx.logger.exception(f"Ошибка при поднятии категории {category_id}")

            if changed:
                save_state(state)

    threading.Thread(target=worker, daemon=True).start()

    @ctx.telegram.command("autoraise")
    def cmd_status(message):
        state = get_state()
        status = "включено ✅" if state.get("enabled") else "выключено ⛔"
        ids = state.get("category_ids", [])
        lines = [
            f"<b>Авто-поднятие лотов</b>: {status}",
            "",
            f"Категории: {', '.join(map(str, ids)) or '—'}",
            "",
            "/autoraise_categories — список ваших категорий с ID",
            "/autoraise_add &lt;id&gt; — добавить категорию",
            "/autoraise_remove &lt;id&gt; — убрать категорию",
            "/autoraise_on — включить",
            "/autoraise_off — выключить",
        ]
        ctx.telegram.reply(message, "\n".join(lines))

    @ctx.telegram.command("autoraise_categories")
    def cmd_categories(message):
        try:
            categories = ctx.account.get_sorted_categories()
        except Exception as e:
            ctx.telegram.reply(message, f"❌ Не удалось получить категории: {e}")
            return
        if not categories:
            ctx.telegram.reply(message, "У вас нет активных категорий с лотами.")
            return
        lines = ["<b>Ваши категории:</b>\n"]
        for cat_id, category in categories.items():
            lines.append(f"• <code>{cat_id}</code> — {category.name}")
        ctx.telegram.reply(message, "\n".join(lines))

    @ctx.telegram.command("autoraise_add")
    def cmd_add(message):
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip().isdigit():
            ctx.telegram.reply(message, "Использование: /autoraise_add &lt;category_id&gt;")
            return
        category_id = int(parts[1].strip())
        state = get_state()
        if category_id in state["category_ids"]:
            ctx.telegram.reply(message, "Эта категория уже добавлена.")
            return
        state["category_ids"].append(category_id)
        save_state(state)
        ctx.telegram.reply(message, f"✅ Категория {category_id} добавлена в авто-поднятие.")

    @ctx.telegram.command("autoraise_remove")
    def cmd_remove(message):
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip().isdigit():
            ctx.telegram.reply(message, "Использование: /autoraise_remove &lt;category_id&gt;")
            return
        category_id = int(parts[1].strip())
        state = get_state()
        if category_id not in state["category_ids"]:
            ctx.telegram.reply(message, "Такой категории нет в списке.")
            return
        state["category_ids"].remove(category_id)
        state["next_attempt"].pop(str(category_id), None)
        save_state(state)
        ctx.telegram.reply(message, f"✅ Категория {category_id} убрана из авто-поднятия.")

    @ctx.telegram.command("autoraise_on")
    def cmd_on(message):
        state = get_state()
        state["enabled"] = True
        save_state(state)
        ctx.telegram.reply(message, "✅ Авто-поднятие включено.")

    @ctx.telegram.command("autoraise_off")
    def cmd_off(message):
        state = get_state()
        state["enabled"] = False
        save_state(state)
        ctx.telegram.reply(message, "⛔ Авто-поднятие выключено.")
