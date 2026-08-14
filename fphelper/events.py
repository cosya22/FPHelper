import logging
from collections import defaultdict
from typing import Callable

from FunPayAPI.common.enums import EventTypes

logger = logging.getLogger("fphelper.events")


class EventBus:
    """Раздаёт события Runner'а FunPay подписавшимся на них плагинам."""

    def __init__(self):
        self._handlers: dict[EventTypes, list[Callable]] = defaultdict(list)

    def subscribe(self, event_type: EventTypes, handler: Callable) -> None:
        self._handlers[event_type].append(handler)

    def dispatch(self, event) -> None:
        for handler in self._handlers.get(event.type, []):
            try:
                handler(event)
            except Exception:
                logger.exception(
                    f"Ошибка в обработчике {getattr(handler, '__module__', '?')}."
                    f"{getattr(handler, '__qualname__', '?')} для события {event.type.name}"
                )
