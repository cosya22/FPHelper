import logging
import threading
import time

from FunPayAPI import Account, Runner

from .events import EventBus

logger = logging.getLogger("fphelper.funpay")

# FunPayAPI.Account.get() сама требует вызывать себя каждые 40-60 минут, чтобы
# обновить PHPSESSID/csrf_token — иначе через какое-то время после старта
# запросы runner/ начинают падать с 400 (сессия протухла). 45 минут — с запасом.
SESSION_REFRESH_INTERVAL = 45 * 60


class FunPayClient:
    """Держит аккаунт FunPay и слушает события через Runner, раздавая их в EventBus."""

    def __init__(self, golden_key: str, bus: EventBus, user_agent: str | None = None, proxy: str | None = None):
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
