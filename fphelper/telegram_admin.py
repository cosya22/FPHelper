import html
import json
import logging
import os
from typing import Callable

from telebot import TeleBot
from telebot.apihelper import ApiTelegramException
from telebot.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .config import Config, hash_password

logger = logging.getLogger("fphelper.telegram")

MENU_MAIN = "menu:main"
MENU_SECTION_PREFIX = "menu:section:"

NOTIFICATION_SETTINGS_PATH = "storage/builtin/notifications.json"

# Тип уведомления -> подпись в меню. "other" — всё, что явно не размечено
# (в т.ч. сторонние плагины) — всегда есть как общий рубильник.
NOTIFICATION_TYPES = {
    "new_message": "💬 Новое сообщение",
    "new_order": "📋 Новый заказ",
    "command_received": "❗ Получена команда",
    "review": "🌟 Оставлен отзыв",
    "delivery": "🚀 Выдача товара",
    "bot_started": "🟢 Запуск бота",
    "other": "🔌 Прочее (плагины)",
}

# Раскладка главного меню по категориям — только для визуальной группировки,
# на доступ и логику не влияет. Разделы, которых нет в списке (в т.ч. плагины),
# попадают в категорию "ПЛАГИНЫ И ПРОЧЕЕ".
SECTION_CATEGORIES: dict[str, list[str]] = {
    "УПРАВЛЕНИЕ": ["👤 Профиль", "💬 Чаты", "📋 Заказы", "🛍️ Лоты", "🌟 Отзывы", "📊 Статистика"],
    "АВТОМАТИЗАЦИЯ": ["⬆️ Авто-поднятие", "🚀 Авто-выдача", "⚡ Быстрые ответы", "❗ Команды", "💸 Авто-вывод"],
    "НАСТРОЙКИ": ["⚙️ Настройки", "🔔 Уведомления", "🚫 Чёрный список"],
    "СИСТЕМА": ["🗒️ Логи", "🧩 Модули"],
}
OTHER_CATEGORY = "ПЛАГИНЫ И ПРОЧЕЕ"

# "Новое сообщение" по умолчанию выключено — иначе при активном чате бот
# засыпает владельца уведомлением на каждую реплику покупателя.
NOTIFICATION_DEFAULTS = {k: (k != "new_message") for k in NOTIFICATION_TYPES}


class TelegramAdmin:
    """
    Обёртка над Telegram-ботом (pyTelegramBotAPI): доступ есть только у владельца
    бота (его Telegram ID задаётся один раз при первом запуске, в config.json).
    Если при настройке задан пароль — владельцу нужно ещё ввести /login <пароль>
    после каждого перезапуска бота, прежде чем откроется меню.

    Кроме команд, есть кнопочное меню: плагины регистрируют свои пункты через
    register_menu_button()/PluginTelegram.menu_item(), а параметризованные действия
    (нужен ID заказа, текст и т.п.) запрашивают текстом через ask().
    """

    def __init__(self, config: Config, config_path: str):
        self.bot = TeleBot(config.telegram.token, parse_mode="HTML")
        self._config = config
        self._config_path = config_path
        self._plugins = []
        self._menu_sections: dict[str, list[tuple[str, str]]] = {}
        self._section_order: list[str] = []
        self._pending: dict[int, Callable[[Message], None]] = {}
        self._authenticated: set[int] = set()
        # ID последнего "висящего" сообщения на чат (ask()-запрос или показанный
        # плагином результат вроде карточки профиля) — чтобы оно не оставалось в
        # чате мусором, когда пользователь уходит в другой раздел/команду.
        self._last_prompt_message: dict[int, int] = {}
        self._wrap_send_message()
        self._register_core_commands()
        self._register_pending_catchall()
        self._setup_bot_menu_button()

    def _wrap_send_message(self) -> None:
        """
        Оборачивает bot.send_message, чтобы ЛЮБОЕ сообщение, отправленное через
        self.bot.send_message (в т.ч. напрямую из плагинов через ctx.telegram.bot),
        запоминалось как "последнее висящее" и подчищалось при переходе в другой
        раздел/команду (см. _clear_pending). notify_owner и первая отправка главного
        меню используют _raw_send_message в обход этого — их удалять не нужно.
        """
        self._raw_send_message = self.bot.send_message

        def tracked_send_message(chat_id, *args, **kwargs):
            sent = self._raw_send_message(chat_id, *args, **kwargs)
            try:
                self._last_prompt_message[chat_id] = sent.message_id
            except AttributeError:
                pass
            return sent

        self.bot.send_message = tracked_send_message

    def is_owner(self, user_id: int) -> bool:
        return user_id == self._config.telegram.owner_id

    def is_authenticated(self, user_id: int) -> bool:
        """Прошёл ли владелец /login в этом запуске бота (если пароль вообще задан)."""
        if not self._config.telegram.password_hash:
            return True
        return user_id in self._authenticated

    def _access_ok(self, user_id: int) -> bool:
        return self.is_owner(user_id) and self.is_authenticated(user_id)

    def set_plugins(self, plugins) -> None:
        self._plugins = plugins

    def _load_notification_settings(self) -> dict:
        if not os.path.exists(NOTIFICATION_SETTINGS_PATH):
            return dict(NOTIFICATION_DEFAULTS)
        with open(NOTIFICATION_SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key, default in NOTIFICATION_DEFAULTS.items():
            data.setdefault(key, default)
        return data

    def _save_notification_settings(self, data: dict) -> None:
        os.makedirs(os.path.dirname(NOTIFICATION_SETTINGS_PATH), exist_ok=True)
        with open(NOTIFICATION_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def is_notification_enabled(self, event_type: str) -> bool:
        return self._load_notification_settings().get(event_type, True)

    def toggle_notification(self, event_type: str) -> bool:
        """Переключает тип уведомления, возвращает новое состояние (включено/выключено)."""
        data = self._load_notification_settings()
        data[event_type] = not data.get(event_type, True)
        self._save_notification_settings(data)
        return data[event_type]

    def notify_owner(self, text: str, event_type: str = "other") -> None:
        if not self.is_notification_enabled(event_type):
            return
        try:
            self._raw_send_message(self._config.telegram.owner_id, text)
        except ApiTelegramException as e:
            if "chat not found" in str(e).lower():
                logger.warning(
                    "Не могу написать владельцу бота: чат не найден. Откройте вашего бота в Telegram "
                    "и нажмите «Start» — боты не могут первыми писать тем, кто ни разу не открывал с ними чат."
                )
            else:
                logger.exception("Не удалось отправить уведомление владельцу бота")
        except Exception:
            logger.exception("Не удалось отправить уведомление владельцу бота")

    def register_command(self, names, handler, owner_only: bool = True) -> None:
        def wrapper(message):
            if owner_only and not self._access_ok(message.from_user.id):
                if self.is_owner(message.from_user.id) and not self.is_authenticated(message.from_user.id):
                    self.bot.reply_to(message, "🔒 Сначала войдите: /login <пароль>")
                return
            self._clear_pending(message.from_user.id, message.chat.id)
            handler(message)

        self.bot.message_handler(commands=list(names))(wrapper)

    def register_callback(self, prefix: str, handler, owner_only: bool = True) -> None:
        def matches(call):
            return call.data == prefix or call.data.startswith(f"{prefix}:")

        def wrapper(call):
            if owner_only and not self._access_ok(call.from_user.id):
                self.bot.answer_callback_query(call.id)
                if self.is_owner(call.from_user.id) and not self.is_authenticated(call.from_user.id):
                    self.bot.send_message(call.message.chat.id, "🔒 Сначала войдите: /login <пароль>")
                return
            try:
                self.bot.answer_callback_query(call.id)
            except Exception:
                pass
            self._clear_pending(call.from_user.id, call.message.chat.id)
            handler(call)

        self.bot.callback_query_handler(func=matches)(wrapper)

    def _clear_pending(self, user_id: int, chat_id: int) -> None:
        """Сбрасывает незавершённый ask() и убирает его сообщение-запрос из чата."""
        self._pending.pop(user_id, None)
        msg_id = self._last_prompt_message.pop(chat_id, None)
        if msg_id:
            try:
                self.bot.delete_message(chat_id, msg_id)
            except Exception:
                pass

    def _setup_bot_menu_button(self) -> None:
        """Кнопка меню со списком команд рядом со скрепкой в поле ввода Telegram."""
        from telebot import types as tg_types

        commands = [
            tg_types.BotCommand("menu", "Открыть меню"),
            tg_types.BotCommand("profile", "Профиль"),
            tg_types.BotCommand("plugins", "Список модулей"),
            tg_types.BotCommand("login", "Войти по паролю"),
            tg_types.BotCommand("cancel", "Отменить текущее действие"),
        ]
        try:
            self.bot.set_my_commands(commands)
            self.bot.set_chat_menu_button(menu_button=tg_types.MenuButtonCommands())
            logger.info(
                "Кнопка меню Telegram настроена. Если она не появилась рядом с полем ввода — "
                "полностью закройте чат с ботом и откройте заново (или перезапустите Telegram), "
                "клиент кеширует её и не всегда обновляет на лету."
            )
        except Exception:
            logger.exception("Не удалось настроить кнопку меню Telegram")

    def register_menu_button(self, section: str, label, callback_data: str, group: str | None = None) -> None:
        """
        Добавляет кнопку в раздел меню (раздел появляется на главном экране автоматически).
        label — строка или функция без аргументов, возвращающая строку (для кнопок-переключателей).
        group — категория внутри раздела для заголовка-разделителя (см. PluginTelegram.menu_item).
        """
        if section not in self._menu_sections:
            self._menu_sections[section] = []
            self._section_order.append(section)
        self._menu_sections[section].append((label, callback_data, group))

    def ask(self, chat_id: int | str, user_id: int, prompt: str, on_answer: Callable[[Message], None]) -> None:
        """
        Отправляет вопрос и ждёт следующее текстовое сообщение от этого пользователя —
        когда оно придёт (и не начинается с "/"), вызывает on_answer(message) один раз.
        Если до этого в чате уже висел неотвеченный запрос — убирает его, чтобы не копился мусор.
        """
        old = self._last_prompt_message.pop(chat_id, None)
        if old:
            try:
                self.bot.delete_message(chat_id, old)
            except Exception:
                pass
        sent = self.bot.send_message(chat_id, f"{prompt}\n\n(или /cancel, чтобы отменить)")
        self._last_prompt_message[chat_id] = sent.message_id
        self._pending[user_id] = on_answer

    def _register_pending_catchall(self) -> None:
        def has_pending(message):
            return message.from_user.id in self._pending and not (message.text or "").startswith("/")

        @self.bot.message_handler(func=has_pending)
        def handle_pending(message):
            callback = self._pending.pop(message.from_user.id, None)
            msg_id = self._last_prompt_message.pop(message.chat.id, None)
            if msg_id:
                try:
                    self.bot.delete_message(message.chat.id, msg_id)
                except Exception:
                    pass
            if callback:
                callback(message)

        @self.bot.message_handler(commands=["cancel"])
        def cmd_cancel(message):
            if not self.is_owner(message.from_user.id):
                return
            had_pending = self._pending.pop(message.from_user.id, None) is not None
            msg_id = self._last_prompt_message.pop(message.chat.id, None)
            if msg_id:
                try:
                    self.bot.delete_message(message.chat.id, msg_id)
                except Exception:
                    pass
            if had_pending:
                self.bot.reply_to(message, "Отменено.")
            else:
                self.bot.reply_to(message, "Нечего отменять.")

    def _main_menu_kb(self) -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=2)

        remaining = list(self._section_order)
        categories = list(SECTION_CATEGORIES.items())
        other_sections = [s for s in remaining if not any(s in secs for _, secs in categories)]
        if other_sections:
            categories = categories + [(OTHER_CATEGORY, other_sections)]

        for category, wanted in categories:
            present = [s for s in wanted if s in remaining]
            if not present:
                continue
            kb.row(InlineKeyboardButton(f"── {category} ──", callback_data="menu:noop"))
            kb.add(*[
                InlineKeyboardButton(s, callback_data=f"{MENU_SECTION_PREFIX}{s}")
                for s in present
            ])
            for s in present:
                remaining.remove(s)
        return kb

    def _section_kb(self, section: str) -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=2)
        items = self._menu_sections.get(section, [])

        groups: dict[str | None, list] = {}
        order: list[str | None] = []
        for label, callback_data, group in items:
            if group not in groups:
                groups[group] = []
                order.append(group)
            groups[group].append((label, callback_data))

        def add_buttons(pairs):
            kb.add(*[
                InlineKeyboardButton(label() if callable(label) else label, callback_data=callback_data)
                for label, callback_data in pairs
            ])

        # кнопки без категории (старые модули, не размечавшие group) — сверху, без заголовка
        if None in groups:
            add_buttons(groups[None])

        for group in order:
            if group is None:
                continue
            kb.row(InlineKeyboardButton(f"── {group} ──", callback_data="menu:noop"))
            add_buttons(groups[group])

        kb.add(InlineKeyboardButton("⬅ Главное меню", callback_data=MENU_MAIN))
        return kb

    def section_keyboard(self, section: str) -> InlineKeyboardMarkup:
        """Публичный доступ к отрисовке раздела — для PluginTelegram.refresh_section()."""
        return self._section_kb(section)

    def _send_or_edit_main_menu(self, chat_id, message_id=None) -> None:
        text = "<b>FPHelper</b>\nВыберите раздел:"
        kb = self._main_menu_kb()
        if message_id:
            self.bot.edit_message_text(text, chat_id, message_id, reply_markup=kb)
        else:
            self._raw_send_message(chat_id, text, reply_markup=kb)

    def _register_core_commands(self) -> None:
        self.register_menu_button("🧩 Модули", "📋 Список модулей и плагинов", "core:plugins")

        @self.bot.message_handler(commands=["login"])
        def cmd_login(message):
            if not self.is_owner(message.from_user.id):
                return
            self._clear_pending(message.from_user.id, message.chat.id)
            if not self._config.telegram.password_hash:
                self.bot.reply_to(message, "Пароль не задан — доступ уже открыт по Telegram ID.")
                return
            parts = message.text.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                self.bot.reply_to(message, "Использование: /login <пароль>")
                return
            if hash_password(parts[1].strip()) == self._config.telegram.password_hash:
                self._authenticated.add(message.from_user.id)
                self.bot.reply_to(message, "✅ Вход выполнен.")
                self._send_or_edit_main_menu(message.chat.id)
            else:
                self.bot.reply_to(message, "❌ Неверный пароль.")

        @self.bot.message_handler(commands=["start", "help", "menu"])
        def cmd_start(message):
            if not self.is_owner(message.from_user.id):
                return
            if not self.is_authenticated(message.from_user.id):
                self.bot.reply_to(message, "🔒 Этот бот защищён паролем. Введите: /login <пароль>")
                return
            self._clear_pending(message.from_user.id, message.chat.id)
            self._send_or_edit_main_menu(message.chat.id)

        @self.bot.message_handler(commands=["plugins"])
        def cmd_plugins(message):
            if not self._access_ok(message.from_user.id):
                return
            self._clear_pending(message.from_user.id, message.chat.id)
            self.bot.reply_to(message, self._plugins_text())

        # --- навигация по меню ---
        @self.bot.callback_query_handler(func=lambda c: c.data == "menu:noop")
        def cbq_noop(call: CallbackQuery):
            self.bot.answer_callback_query(call.id)

        @self.bot.callback_query_handler(func=lambda c: c.data == MENU_MAIN)
        def cbq_main(call: CallbackQuery):
            self.bot.answer_callback_query(call.id)
            if not self._access_ok(call.from_user.id):
                return
            self._clear_pending(call.from_user.id, call.message.chat.id)
            self._send_or_edit_main_menu(call.message.chat.id, call.message.message_id)

        @self.bot.callback_query_handler(func=lambda c: c.data.startswith(MENU_SECTION_PREFIX))
        def cbq_section(call: CallbackQuery):
            self.bot.answer_callback_query(call.id)
            if not self._access_ok(call.from_user.id):
                return
            self._clear_pending(call.from_user.id, call.message.chat.id)
            section = call.data[len(MENU_SECTION_PREFIX):]
            self.bot.edit_message_text(
                f"<b>{section}</b>",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=self._section_kb(section),
            )

        @self.bot.callback_query_handler(func=lambda c: c.data == "core:plugins")
        def cbq_plugins(call: CallbackQuery):
            self.bot.answer_callback_query(call.id)
            if not self._access_ok(call.from_user.id):
                return
            if not self._plugins:
                self.bot.send_message(call.message.chat.id, "Нет загруженных модулей.")
                return
            kb = InlineKeyboardMarkup(row_width=2)
            kb.add(*[
                InlineKeyboardButton(p.info.name, callback_data=f"core:plugin_info:{i}")
                for i, p in enumerate(self._plugins)
            ])
            self.bot.send_message(call.message.chat.id, "<b>Модули и плагины:</b>\nВыберите, чтобы открыть карточку.", reply_markup=kb)

        @self.bot.callback_query_handler(func=lambda c: c.data.startswith("core:plugin_info:"))
        def cbq_plugin_info(call: CallbackQuery):
            self.bot.answer_callback_query(call.id)
            if not self._access_ok(call.from_user.id):
                return
            try:
                p = self._plugins[int(call.data.rsplit(":", 1)[-1])]
            except (ValueError, IndexError):
                return

            kind = "Встроенный модуль" if getattr(p, "builtin", False) else "Плагин"
            text = (
                f"<b>{html.escape(p.info.name)}</b> v{html.escape(str(p.info.version))}\n"
                f"{kind}\n\n{html.escape(p.info.description)}"
            )

            # если у плагина есть свой раздел меню с похожим названием — дадим кнопку сразу туда
            matching_section = next(
                (s for s in self._section_order if p.info.name.lower() in s.lower()), None
            )
            kb = None
            if matching_section:
                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton("⚙️ Открыть меню плагина", callback_data=f"{MENU_SECTION_PREFIX}{matching_section}"))

            self.bot.send_message(call.message.chat.id, text, reply_markup=kb)

        def line(p) -> str:
            # экранируем — описание может прийти из стороннего плагина и содержать
            # символы, которые Telegram примет за (нерабочую) HTML-разметку
            name = html.escape(p.info.name)
            version = html.escape(str(p.info.version))
            description = html.escape(p.info.description)
            return f"• <b>{name}</b> v{version} — {description}"

        builtin = [p for p in self._plugins if getattr(p, "builtin", False)]
        custom = [p for p in self._plugins if not getattr(p, "builtin", False)]
        lines = []
        if builtin:
            lines.append("<b>Встроенные модули:</b>\n")
            lines.extend(line(p) for p in builtin)
        if custom:
            if lines:
                lines.append("")
            lines.append("<b>Плагины:</b>\n")
            lines.extend(line(p) for p in custom)
        return "\n".join(lines)

    def run(self) -> None:
        logger.info("Telegram-бот запущен (polling)")
        self.bot.infinity_polling(skip_pending=True)
