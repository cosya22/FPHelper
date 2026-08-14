import logging

from telebot import TeleBot

from .config import Config, save_config

logger = logging.getLogger("fphelper.telegram")


class TelegramAdmin:
    """
    Обёртка над Telegram-ботом (pyTelegramBotAPI): доступ к командам только у
    администраторов из белого списка config.telegram.admins. Список админов можно
    расширять прямо из чата — /whoami не требует прав, остальные команды требуют.
    """

    def __init__(self, config: Config, config_path: str):
        self.bot = TeleBot(config.telegram.token, parse_mode="HTML")
        self._config = config
        self._config_path = config_path
        self._plugins = []
        self._register_core_commands()

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
            handler(call)

        self.bot.callback_query_handler(func=matches)(wrapper)

    def _register_core_commands(self) -> None:
        @self.bot.message_handler(commands=["whoami"])
        def cmd_whoami(message):
            self.bot.reply_to(message, f"Ваш Telegram ID: <code>{message.from_user.id}</code>")

        @self.bot.message_handler(commands=["start", "help"])
        def cmd_start(message):
            if not self.is_admin(message.from_user.id):
                self.bot.reply_to(
                    message,
                    "⛔ У вас нет доступа к этому боту.\n\n"
                    "Отправьте /whoami, чтобы узнать свой Telegram ID, и попросите "
                    "действующего админа добавить вас командой /addadmin.",
                )
                return
            lines = [
                "<b>FPHelper</b>\n",
                "/whoami — узнать свой Telegram ID",
                "/admins — список админов",
                "/addadmin &lt;id&gt; — добавить админа",
                "/deladmin &lt;id&gt; — удалить админа",
                "/plugins — список загруженных плагинов",
            ]
            self.bot.reply_to(message, "\n".join(lines))

        @self.bot.message_handler(commands=["admins"])
        def cmd_admins(message):
            if not self.is_admin(message.from_user.id):
                self.bot.reply_to(message, "⛔ Нет доступа.")
                return
            admins = self._config.telegram.admins
            text = "<b>Админы:</b>\n" + "\n".join(f"• <code>{a}</code>" for a in admins)
            self.bot.reply_to(message, text)

        @self.bot.message_handler(commands=["addadmin"])
        def cmd_addadmin(message):
            if not self.is_admin(message.from_user.id):
                self.bot.reply_to(message, "⛔ Нет доступа.")
                return
            parts = message.text.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip().isdigit():
                self.bot.reply_to(message, "Использование: /addadmin &lt;telegram_id&gt;")
                return
            new_id = int(parts[1].strip())
            if self.add_admin(new_id):
                self.bot.reply_to(message, f"✅ Админ <code>{new_id}</code> добавлен.")
            else:
                self.bot.reply_to(message, "Этот пользователь уже админ.")

        @self.bot.message_handler(commands=["deladmin"])
        def cmd_deladmin(message):
            if not self.is_admin(message.from_user.id):
                self.bot.reply_to(message, "⛔ Нет доступа.")
                return
            parts = message.text.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip().isdigit():
                self.bot.reply_to(message, "Использование: /deladmin &lt;telegram_id&gt;")
                return
            target_id = int(parts[1].strip())
            if target_id == message.from_user.id:
                self.bot.reply_to(message, "❌ Нельзя удалить самого себя.")
                return
            if self.remove_admin(target_id):
                self.bot.reply_to(message, f"✅ Админ <code>{target_id}</code> удалён.")
            else:
                self.bot.reply_to(message, "Этот пользователь не найден среди админов.")

        @self.bot.message_handler(commands=["plugins"])
        def cmd_plugins(message):
            if not self.is_admin(message.from_user.id):
                self.bot.reply_to(message, "⛔ Нет доступа.")
                return
            if not self._plugins:
                self.bot.reply_to(message, "Нет загруженных плагинов.")
                return
            lines = ["<b>Загруженные плагины:</b>\n"]
            for p in self._plugins:
                lines.append(f"• <b>{p.info.name}</b> v{p.info.version} — {p.info.description}")
            self.bot.reply_to(message, "\n".join(lines))

    def run(self) -> None:
        logger.info("Telegram-бот запущен (polling)")
        self.bot.infinity_polling(skip_pending=True)
