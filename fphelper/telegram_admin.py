import html
import logging
from typing import Callable

from telebot import TeleBot
from telebot.apihelper import ApiTelegramException
from telebot.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .config import Config

logger = logging.getLogger("fphelper.telegram")

MENU_MAIN = "menu:main"
MENU_SECTION_PREFIX = "menu:section:"


class TelegramAdmin:
    """
    Обёртка над Telegram-ботом (pyTelegramBotAPI): доступ есть только у владельца
    бота (его Telegram ID задаётся один раз при первом запуске, в config.json).

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

    def is_owner(self, user_id: int) -> bool:
        return user_id == self._config.telegram.owner_id

    def set_plugins(self, plugins) -> None:
        self._plugins = plugins

    def notify_owner(self, text: str) -> None:
        try:
            self.bot.send_message(self._config.telegram.owner_id, text)
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
            if owner_only and not self.is_owner(message.from_user.id):
                return
            handler(message)

        self.bot.message_handler(commands=list(names))(wrapper)

    def register_callback(self, prefix: str, handler, owner_only: bool = True) -> None:
        def matches(call):
            return call.data == prefix or call.data.startswith(f"{prefix}:")

        def wrapper(call):
            if owner_only and not self.is_owner(call.from_user.id):
                self.bot.answer_callback_query(call.id)
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
            if not self.is_owner(message.from_user.id):
                return
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
        self.register_menu_button("🧩 Модули", "📋 Список модулей и плагинов", "core:plugins")

        @self.bot.message_handler(commands=["start", "help", "menu"])
        def cmd_start(message):
            if not self.is_owner(message.from_user.id):
                return
            self._send_or_edit_main_menu(message.chat.id)

        @self.bot.message_handler(commands=["plugins"])
        def cmd_plugins(message):
            if not self.is_owner(message.from_user.id):
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

        @self.bot.callback_query_handler(func=lambda c: c.data == "core:plugins")
        def cbq_plugins(call: CallbackQuery):
            self.bot.answer_callback_query(call.id)
            self.bot.send_message(call.message.chat.id, self._plugins_text())

    def _plugins_text(self) -> str:
        if not self._plugins:
            return "Нет загруженных модулей."

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
