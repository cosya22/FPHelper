import logging
from typing import Callable

from telebot import TeleBot
from telebot.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .config import Config, save_config

logger = logging.getLogger("fphelper.telegram")

MENU_MAIN = "menu:main"
MENU_SECTION_PREFIX = "menu:section:"


class TelegramAdmin:
    """
    Обёртка над Telegram-ботом (pyTelegramBotAPI): доступ к командам только у
    администраторов из белого списка config.telegram.admins. Список админов можно
    расширять прямо из чата — /whoami не требует прав, остальные команды требуют.

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
        self._register_core_commands()
        self._register_pending_catchall()

    def is_admin(self, user_id: int) -> bool:
        return user_id in self._config.telegram.admins

    def add_admin(self, user_id: int) -> bool:
        if user_id in self._config.telegram.admins:
            return False
        self._config.telegram.admins.append(user_id)
        save_config(self._config, self._config_path)
        return True

    def remove_admin(self, user_id: int) -> bool:
        if user_id not in self._config.telegram.admins:
            return False
        self._config.telegram.admins.remove(user_id)
        save_config(self._config, self._config_path)
        return True

    def set_plugins(self, plugins) -> None:
        self._plugins = plugins

    def notify_admins(self, text: str) -> None:
        for admin_id in list(self._config.telegram.admins):
            try:
                self.bot.send_message(admin_id, text)
            except Exception:
                logger.exception(f"Не удалось отправить уведомление админу {admin_id}")

    def register_command(self, names, handler, admin_only: bool = True) -> None:
        def wrapper(message):
            if admin_only and not self.is_admin(message.from_user.id):
                self.bot.reply_to(message, "⛔ У вас нет доступа к этой команде.")
                return
            handler(message)

        self.bot.message_handler(commands=list(names))(wrapper)

    def register_callback(self, prefix: str, handler, admin_only: bool = True) -> None:
        def matches(call):
            return call.data == prefix or call.data.startswith(f"{prefix}:")

        def wrapper(call):
            if admin_only and not self.is_admin(call.from_user.id):
                self.bot.answer_callback_query(call.id, "⛔ Нет доступа")
                return
            try:
                self.bot.answer_callback_query(call.id)
            except Exception:
                pass
            handler(call)

        self.bot.callback_query_handler(func=matches)(wrapper)

    def register_menu_button(self, section: str, label: str, callback_data: str) -> None:
        """Добавляет кнопку в раздел меню (раздел появляется на главном экране автоматически)."""
        if section not in self._menu_sections:
            self._menu_sections[section] = []
            self._section_order.append(section)
        self._menu_sections[section].append((label, callback_data))

    def ask(self, chat_id: int | str, user_id: int, prompt: str, on_answer: Callable[[Message], None]) -> None:
        """
        Отправляет вопрос и ждёт следующее текстовое сообщение от этого пользователя —
        когда оно придёт (и не начинается с "/"), вызывает on_answer(message) один раз.
        """
        self.bot.send_message(chat_id, f"{prompt}\n\n(или /cancel, чтобы отменить)")
        self._pending[user_id] = on_answer

    def _register_pending_catchall(self) -> None:
        def has_pending(message):
            return message.from_user.id in self._pending and not (message.text or "").startswith("/")

        @self.bot.message_handler(func=has_pending)
        def handle_pending(message):
            callback = self._pending.pop(message.from_user.id, None)
            if callback:
                callback(message)

        @self.bot.message_handler(commands=["cancel"])
        def cmd_cancel(message):
            if self._pending.pop(message.from_user.id, None) is not None:
                self.bot.reply_to(message, "Отменено.")
            else:
                self.bot.reply_to(message, "Нечего отменять.")

    def _main_menu_kb(self) -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup()
        for section in self._section_order:
            kb.add(InlineKeyboardButton(section, callback_data=f"{MENU_SECTION_PREFIX}{section}"))
        return kb

    def _section_kb(self, section: str) -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup()
        for label, callback_data in self._menu_sections.get(section, []):
            kb.add(InlineKeyboardButton(label, callback_data=callback_data))
        kb.add(InlineKeyboardButton("⬅ Главное меню", callback_data=MENU_MAIN))
        return kb

    def _send_or_edit_main_menu(self, chat_id, message_id=None) -> None:
        text = "<b>FPHelper</b>\nВыберите раздел:"
        kb = self._main_menu_kb()
        if message_id:
            self.bot.edit_message_text(text, chat_id, message_id, reply_markup=kb)
        else:
            self.bot.send_message(chat_id, text, reply_markup=kb)

    def _register_core_commands(self) -> None:
        # --- регистрация в меню собственных разделов ядра ---
        self.register_menu_button("👥 Админы", "🆔 Мой ID", "core:whoami")
        self.register_menu_button("👥 Админы", "📋 Список", "core:admins")
        self.register_menu_button("👥 Админы", "➕ Добавить", "core:addadmin_ask")
        self.register_menu_button("👥 Админы", "➖ Удалить", "core:deladmin_ask")
        self.register_menu_button("🧩 Плагины", "📋 Список плагинов", "core:plugins")

        @self.bot.message_handler(commands=["whoami"])
        def cmd_whoami(message):
            self.bot.reply_to(message, f"Ваш Telegram ID: <code>{message.from_user.id}</code>")

        @self.bot.message_handler(commands=["start", "help", "menu"])
        def cmd_start(message):
            if not self.is_admin(message.from_user.id):
                self.bot.reply_to(
                    message,
                    "⛔ У вас нет доступа к этому боту.\n\n"
                    "Отправьте /whoami, чтобы узнать свой Telegram ID, и попросите "
                    "действующего админа добавить вас командой /addadmin.",
                )
                return
            self._send_or_edit_main_menu(message.chat.id)

        @self.bot.message_handler(commands=["admins"])
        def cmd_admins(message):
            if not self.is_admin(message.from_user.id):
                self.bot.reply_to(message, "⛔ Нет доступа.")
                return
            self.bot.reply_to(message, self._admins_text())

        @self.bot.message_handler(commands=["addadmin"])
        def cmd_addadmin(message):
            if not self.is_admin(message.from_user.id):
                self.bot.reply_to(message, "⛔ Нет доступа.")
                return
            parts = message.text.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip().isdigit():
                self.bot.reply_to(message, "Использование: /addadmin &lt;telegram_id&gt;")
                return
            self._do_add_admin(message, parts[1].strip())

        @self.bot.message_handler(commands=["deladmin"])
        def cmd_deladmin(message):
            if not self.is_admin(message.from_user.id):
                self.bot.reply_to(message, "⛔ Нет доступа.")
                return
            parts = message.text.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip().isdigit():
                self.bot.reply_to(message, "Использование: /deladmin &lt;telegram_id&gt;")
                return
            self._do_del_admin(message, parts[1].strip())

        @self.bot.message_handler(commands=["plugins"])
        def cmd_plugins(message):
            if not self.is_admin(message.from_user.id):
                self.bot.reply_to(message, "⛔ Нет доступа.")
                return
            self.bot.reply_to(message, self._plugins_text())

        # --- навигация по меню ---
        @self.bot.callback_query_handler(func=lambda c: c.data == MENU_MAIN)
        def cbq_main(call: CallbackQuery):
            self.bot.answer_callback_query(call.id)
            self._send_or_edit_main_menu(call.message.chat.id, call.message.message_id)

        @self.bot.callback_query_handler(func=lambda c: c.data.startswith(MENU_SECTION_PREFIX))
        def cbq_section(call: CallbackQuery):
            self.bot.answer_callback_query(call.id)
            section = call.data[len(MENU_SECTION_PREFIX):]
            self.bot.edit_message_text(
                f"<b>{section}</b>",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=self._section_kb(section),
            )

        # --- кнопки раздела "Админы"/"Плагины" ---
        @self.bot.callback_query_handler(func=lambda c: c.data == "core:whoami")
        def cbq_whoami(call: CallbackQuery):
            self.bot.answer_callback_query(call.id, f"Ваш ID: {call.from_user.id}", show_alert=True)

        @self.bot.callback_query_handler(func=lambda c: c.data == "core:admins")
        def cbq_admins(call: CallbackQuery):
            self.bot.answer_callback_query(call.id)
            self.bot.send_message(call.message.chat.id, self._admins_text())

        @self.bot.callback_query_handler(func=lambda c: c.data == "core:plugins")
        def cbq_plugins(call: CallbackQuery):
            self.bot.answer_callback_query(call.id)
            self.bot.send_message(call.message.chat.id, self._plugins_text())

        @self.bot.callback_query_handler(func=lambda c: c.data == "core:addadmin_ask")
        def cbq_addadmin_ask(call: CallbackQuery):
            self.bot.answer_callback_query(call.id)
            self.ask(
                call.message.chat.id, call.from_user.id,
                "Пришлите Telegram ID нового админа.",
                lambda message: self._do_add_admin(message, message.text.strip()),
            )

        @self.bot.callback_query_handler(func=lambda c: c.data == "core:deladmin_ask")
        def cbq_deladmin_ask(call: CallbackQuery):
            self.bot.answer_callback_query(call.id)
            self.ask(
                call.message.chat.id, call.from_user.id,
                "Пришлите Telegram ID админа, которого нужно удалить.",
                lambda message: self._do_del_admin(message, message.text.strip()),
            )

    def _admins_text(self) -> str:
        admins = self._config.telegram.admins
        return "<b>Админы:</b>\n" + "\n".join(f"• <code>{a}</code>" for a in admins)

    def _plugins_text(self) -> str:
        if not self._plugins:
            return "Нет загруженных плагинов."
        lines = ["<b>Загруженные плагины:</b>\n"]
        for p in self._plugins:
            lines.append(f"• <b>{p.info.name}</b> v{p.info.version} — {p.info.description}")
        return "\n".join(lines)

    def _do_add_admin(self, message: Message, raw_id: str) -> None:
        if not raw_id.isdigit():
            self.bot.reply_to(message, "ID должен быть числом.")
            return
        new_id = int(raw_id)
        if self.add_admin(new_id):
            self.bot.reply_to(message, f"✅ Админ <code>{new_id}</code> добавлен.")
        else:
            self.bot.reply_to(message, "Этот пользователь уже админ.")

    def _do_del_admin(self, message: Message, raw_id: str) -> None:
        if not raw_id.isdigit():
            self.bot.reply_to(message, "ID должен быть числом.")
            return
        target_id = int(raw_id)
        if target_id == message.from_user.id:
            self.bot.reply_to(message, "❌ Нельзя удалить самого себя.")
            return
        if self.remove_admin(target_id):
            self.bot.reply_to(message, f"✅ Админ <code>{target_id}</code> удалён.")
        else:
            self.bot.reply_to(message, "Этот пользователь не найден среди админов.")

    def run(self) -> None:
        logger.info("Telegram-бот запущен (polling)")
        self.bot.infinity_polling(skip_pending=True)
