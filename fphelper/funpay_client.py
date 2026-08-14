import logging

from FunPayAPI import Account, Runner

from .events import EventBus

logger = logging.getLogger("fphelper.funpay")


class FunPayClient:
    """Держит аккаунт FunPay и слушает события через Runner, раздавая их в EventBus."""

    def __init__(self, golden_key: str, bus: EventBus, user_agent: str | None = None, proxy: str | None = None):
        self.bus = bus
        proxy_dict = {"http": proxy, "https": proxy} if proxy else None
        self.account = Account(golden_key, user_agent=user_agent or None, proxy=proxy_dict).get()

    def run(self, requests_delay: float = 6.0) -> None:
        runner = Runner(self.account)
        logger.info("Слушаю события FunPay...")
        for event in runner.listen(requests_delay=requests_delay):
            self.bus.dispatch(event)
