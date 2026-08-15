import logging
import threading
import time

import requests as requests_lib
from FunPayAPI import Account, Runner
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


class FunPayClient:
    """Держит аккаунт FunPay и слушает события через Runner, раздавая их в EventBus."""

    def __init__(self, golden_key: str, bus: EventBus, user_agent: str | None = None, proxy: str | None = None):
        _patch_golden_seal_support()
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
