from dataclasses import dataclass
from logging import Logger
from typing import Callable

from FunPayAPI.account import Account
from FunPayAPI.common.enums import EventTypes

from .events import EventBus
from .storage import PluginStorage


@dataclass
class PluginInfo:
    name: str
    version: str = "0.1.0"
    description: str = ""
    author: str = ""


class PluginEvents:
    """Декораторы для подписки плагина на события FunPay."""

    def __init__(self, bus: EventBus):
        self._bus = bus

    def new_message(self, func):
        self._bus.subscribe(EventTypes.NEW_MESSAGE, func)
        return func

    def new_order(self, func):
        self._bus.subscribe(EventTypes.NEW_ORDER, func)
        return func

    def order_status_changed(self, func):
        self._bus.subscribe(EventTypes.ORDER_STATUS_CHANGED, func)
        return func

    def chats_list_changed(self, func):
        self._bus.subscribe(EventTypes.CHATS_LIST_CHANGED, func)
        return func

    def orders_list_changed(self, func):
        self._bus.subscribe(EventTypes.ORDERS_LIST_CHANGED, func)
        return func


class PluginTelegram:
    """Регистрация Telegram-команд/колбэков плагина в общем боте-админке."""

    def __init__(self, admin):
        self._admin = admin

    def command(self, *names: str, admin_only: bool = True):
        def deco(func):
            self._admin.register_command(names, func, admin_only=admin_only)
            return func
        return deco

    def callback(self, prefix: str, admin_only: bool = True):
        def deco(func):
            self._admin.register_callback(prefix, func, admin_only=admin_only)
            return func
        return deco

    def reply(self, message, text: str, **kwargs):
        return self._admin.bot.reply_to(message, text, **kwargs)

    def send(self, chat_id: int, text: str, **kwargs):
        return self._admin.bot.send_message(chat_id, text, **kwargs)

    def is_admin(self, user_id: int) -> bool:
        return self._admin.is_admin(user_id)

    @property
    def bot(self):
        return self._admin.bot


@dataclass
class PluginContext:
    """
    Всё, что получает плагин при загрузке. account — для действий на FunPay,
    events/telegram — для подписки на события и команды, storage — приватное
    JSON-хранилище плагина, notify_admins — быстрая рассылка всем админам.
    """

    account: Account
    events: PluginEvents
    telegram: PluginTelegram
    storage: PluginStorage
    logger: Logger
    notify_admins: Callable[[str], None]
