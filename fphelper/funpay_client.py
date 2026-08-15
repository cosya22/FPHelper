import logging
import threading
import time

import requests as requests_lib
from bs4 import BeautifulSoup
from FunPayAPI import Account, Runner
from FunPayAPI import types as funpay_types
from FunPayAPI.common import exceptions as funpay_exceptions

from .events import EventBus

logger = logging.getLogger("fphelper.funpay")

# FunPayAPI.Account.get() сама требует вызывать себя каждые 40-60 минут, чтобы
# обновить PHPSESSID/csrf_token — иначе через какое-то время после старта
# запросы runner/ начинают падать с 400 (сессия протухла). 45 минут — с запасом.
SESSION_REFRESH_INTERVAL = 45 * 60

_golden_seal_patched = False


def _patch_golden_seal_support() -> None:
    """
    FunPay в какой-то момент добавил вторую обязательную куку golden_seal (в паре
    с golden_key) — без неё запросы к runner/ падают с "Необходимая cookie
    отсутствует или устарела". Установленная FunPayAPI про неё не знает: сервер
    её присылает (Set-Cookie), но библиотека никогда не сохраняет и не пересылает
    её обратно. Патчим Account.method(), чтобы ловить и пересылать её тоже —
    без правки самого пакета в site-packages (не переживёт переустановку).
    """
    global _golden_seal_patched
    if _golden_seal_patched:
        return

    def patched_method(self, request_method, api_method, headers, payload,
                        exclude_phpsessid: bool = False, raise_not_200: bool = False):
        headers["cookie"] = f"golden_key={self.golden_key}"
        if self.phpsessid and not exclude_phpsessid:
            headers["cookie"] += f"; PHPSESSID={self.phpsessid}"
        golden_seal = getattr(self, "golden_seal", None)
        if golden_seal:
            headers["cookie"] += f"; golden_seal={golden_seal}"
        if self.user_agent:
            headers["user-agent"] = self.user_agent

        link = api_method if api_method.startswith("https://funpay.com") else "https://funpay.com/" + api_method
        response = getattr(requests_lib, request_method)(
            link, headers=headers, data=payload, timeout=self.requests_timeout, proxies=self.proxy or {}
        )

        new_seal = response.cookies.get("golden_seal")
        if new_seal:
            self.golden_seal = new_seal

        if response.status_code == 403:
            raise funpay_exceptions.UnauthorizedError(response)
        elif response.status_code != 200 and raise_not_200:
            raise funpay_exceptions.RequestFailedError(response)
        return response

    Account.method = patched_method
    _golden_seal_patched = True


_chat_history_logging_patched = False


def _patch_chat_history_error_logging() -> None:
    """
    Runner.generate_new_message_events() при любой ошибке get_chats_histories()
    (даже не связанной с HTTP-статусом, например KeyError при разборе ответа
    FunPay) молча пишет только "Не удалось получить истории чатов [id]." и
    полный traceback шлёт лишь на DEBUG — а его мы намеренно не включаем на
    постоянку (см. main.py: слишком шумно, дампит HTML на каждый опрос).
    Патчим именно этот метод, чтобы при ошибке видеть настоящую причину в ERROR-логе,
    не включая DEBUG для всей FunPayAPI.
    """
    global _chat_history_logging_patched
    if _chat_history_logging_patched:
        return

    original = Account.get_chats_histories

    def patched(self, chats_data):
        try:
            return original(self, chats_data)
        except Exception:
            logger.exception(f"Ошибка при получении истории чатов {list(chats_data.keys())}")
            raise

    Account.get_chats_histories = patched
    _chat_history_logging_patched = True


_parse_messages_patched = False


def _patch_parse_messages_robustness() -> None:
    """
    FunPayAPI.Account.__parse_messages падает AttributeError, если у сообщения нет
    ожидаемого <div class="message-text"> (встречаются системные/нестандартные
    сообщения, для которых библиотека не предусмотрела разбор) — из-за этого вся
    история чата не приходит, Runner несколько раз впустую повторяет запрос и в
    итоге сдаётся ("превышено кол-во попыток"), а чат так и не обрабатывается.
    Патчим на более отказоустойчивую версию: при отсутствии ожидаемого блока
    подставляем пустой текст вместо падения. Заодно чиним баг апстрима —
    `self.chat_id_private` (без вызова) в оригинале всегда truthy, чекбокс "это
    личный чат" эффективно никогда не проверялся.
    """
    global _parse_messages_patched
    if _parse_messages_patched:
        return

    bot_character_attr = "_Account__bot_character"

    def patched(self, json_messages, chat_id, interlocutor_id=None, interlocutor_username=None, from_id=0):
        messages = []
        ids = {self.id: self.username, 0: "FunPay"}
        badges = {}
        if interlocutor_id is not None:
            ids[interlocutor_id] = interlocutor_username

        for i in json_messages:
            if i["id"] < from_id:
                continue
            author_id = i["author"]
            parser = BeautifulSoup(i["html"], "html.parser")

            if None in [ids.get(author_id), badges.get(author_id)] and \
                    (author_div := parser.find("div", {"class": "media-user-name"})):
                if badges.get(author_id) is None:
                    badge = author_div.find("span")
                    badges[author_id] = badge.text if badge else 0
                if ids.get(author_id) is None:
                    author_a = author_div.find("a")
                    author = author_a.text.strip() if author_a else None
                    if author:
                        ids[author_id] = author
                        if self.chat_id_private(chat_id) and author_id == interlocutor_id and not interlocutor_username:
                            interlocutor_username = author
                            ids[interlocutor_id] = interlocutor_username

            image_tag = parser.find("a", {"class": "chat-img-link"})
            if self.chat_id_private(chat_id) and image_tag:
                image_link = image_tag.get("href")
                message_text = None
            else:
                image_link = None
                # FunPay сменил вёрстку: раньше текст лежал в div.message-text, теперь —
                # в div.chat-msg-text (подтверждено реальным HTML из лога пользователя,
                # 15.08.2026). Системные строки (author_id == 0) по-прежнему пробуем через
                # старый alert-класс первым, но chat-msg-text — как рабочий запасной вариант.
                candidates = (
                    ["alert alert-with-icon alert-info", "chat-msg-text"]
                    if author_id == 0 else
                    ["chat-msg-text", "message-text"]
                )
                node = None
                for css_class in candidates:
                    node = parser.find("div", {"class": css_class})
                    if node:
                        break
                if node:
                    message_text = node.text.strip()
                else:
                    message_text = ""
                    # Ни один из известных селекторов не подошёл — логируем HTML, чтобы
                    # понять, что это за сообщение (см. _patch_parse_messages_robustness).
                    logger.warning(
                        f"Сообщение id={i.get('id')} (author_id={author_id}) в чате {chat_id}: "
                        f"не найден ожидаемый блок текста в HTML, текст будет пустым. "
                        f"HTML (обрезано до 500 симв.): {i.get('html', '')[:500]}"
                    )

            bot_character = getattr(self, bot_character_attr)
            by_bot = False
            if not image_link and message_text and message_text.startswith(bot_character):
                message_text = message_text.replace(bot_character, "", 1)
                by_bot = True

            message_obj = funpay_types.Message(i["id"], message_text, chat_id, interlocutor_username,
                                               None, author_id, i["html"], image_link, determine_msg_type=False)
            message_obj.by_bot = by_bot
            message_obj.type = funpay_types.MessageTypes.NON_SYSTEM if author_id != 0 else message_obj.get_message_type()
            messages.append(message_obj)

        for i in messages:
            i.author = ids.get(i.author_id)
            i.chat_name = interlocutor_username
            i.badge = badges.get(i.author_id) if badges.get(i.author_id) != 0 else None
        return messages

    Account._Account__parse_messages = patched
    _parse_messages_patched = True


class FunPayClient:
    """Держит аккаунт FunPay и слушает события через Runner, раздавая их в EventBus."""

    def __init__(self, golden_key: str, bus: EventBus, user_agent: str | None = None, proxy: str | None = None):
        _patch_golden_seal_support()
        _patch_chat_history_error_logging()
        _patch_parse_messages_robustness()
        self.bus = bus
        proxy_dict = {"http": proxy, "https": proxy} if proxy else None
        self.account = Account(golden_key, user_agent=user_agent or None, proxy=proxy_dict).get()

    def _session_refresh_worker(self) -> None:
        while True:
            time.sleep(SESSION_REFRESH_INTERVAL)
            try:
                self.account.get(update_phpsessid=True)
                logger.info("Сессия FunPay обновлена (PHPSESSID/csrf_token)")
            except Exception:
                logger.exception("Не удалось обновить сессию FunPay")

    def run(self, requests_delay: float = 6.0) -> None:
        threading.Thread(target=self._session_refresh_worker, daemon=True).start()
        runner = Runner(self.account)
        logger.info("Слушаю события FunPay...")
        for event in runner.listen(requests_delay=requests_delay):
            self.bus.dispatch(event)
