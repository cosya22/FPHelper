import logging
import os
import sys
import threading

from colorama import Fore, Style, init as colorama_init

from fphelper.config import CONFIG_PATH, load_or_create_config
from fphelper.events import EventBus
from fphelper.funpay_client import FunPayClient
from fphelper.plugin_manager import load_builtin, load_plugins
from fphelper.telegram_admin import TelegramAdmin


def patch_request_error_logging() -> None:
    """
    FunPayAPI.RequestFailedError хранит тело ответа FunPay (response.text), но не
    показывает его в str(e) — а именно str(e) попадает в наш DEBUG-лог traceback'а.
    Добавляем тело ответа, чтобы при 400/403 и т.п. было видно, что именно ответил
    FunPay, а не только код статуса.
    """
    from FunPayAPI.common.exceptions import RequestFailedError

    original_str = RequestFailedError.__str__

    def patched_str(self):
        try:
            body = self.response.text[:500]
        except Exception:
            body = "<не удалось прочитать тело ответа>"
        return f"{original_str(self)}\nТело ответа FunPay: {body}"

    RequestFailedError.__str__ = patched_str

_LEVEL_COLORS = {
    logging.DEBUG: Fore.BLACK + Style.BRIGHT,
    logging.INFO: Fore.CYAN,
    logging.WARNING: Fore.YELLOW,
    logging.ERROR: Fore.RED,
    logging.CRITICAL: Fore.RED + Style.BRIGHT,
}


class ColorFormatter(logging.Formatter):
    """Раскрашивает строку лога по уровню — только для консоли, в файл пишется как обычно."""

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        color = _LEVEL_COLORS.get(record.levelno, "")
        return f"{color}{message}{Style.RESET_ALL}" if color else message


def print_banner() -> None:
    width = 62
    border = "─" * width
    lines = [
        f"┌{border}┐",
        f"│{'FPHelper'.center(width)}│",
        f"│{'бот-помощник для продавцов FunPay'.center(width)}│",
        f"├{border}┤",
        f"│{'github.com/cosya22/FPHelper'.center(width)}│",
        f"└{border}┘",
    ]
    print()
    for line in lines:
        print(f"{Fore.CYAN}{Style.BRIGHT}{line}{Style.RESET_ALL}")
    print()


def print_profile_card(account, balance) -> None:
    width = 54

    def row(text: str) -> str:
        return f"│ {text.ljust(width - 2)} │"

    border = "─" * width
    lines = [
        f"┌{border}┐",
        row(f"Аккаунт: {account.username}  (ID {account.id})"),
        row(f"Баланс: {balance.total_rub:.2f} RUB · {balance.total_usd:.2f} USD · {balance.total_eur:.2f} EUR"),
        row(f"Активных продаж: {account.active_sales}, покупок: {account.active_purchases}"),
        f"└{border}┘",
    ]
    print()
    for line in lines:
        print(f"{Fore.GREEN}{Style.BRIGHT}{line}{Style.RESET_ALL}")
    print()


def setup_logging() -> None:
    os.makedirs("logs", exist_ok=True)
    colorama_init()

    # На Windows консоль часто в cp1251/cp866 и падает на эмодзи в логах.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    fmt = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ColorFormatter(fmt))
    file_handler = logging.FileHandler("logs/fphelper.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(fmt))

    logging.basicConfig(level=logging.INFO, handlers=[console_handler, file_handler])

    # Тело ответа FunPay при ошибках запросов добавляем в текст исключения —
    # пригодится, если что-то сломается, но само по себе ничего не логирует
    # и не шумит, в отличие от DEBUG-уровня всей FunPayAPI (специально не
    # включаем его на постоянной основе — он на каждый опрос дампит полный
    # HTML переписки в лог).
    patch_request_error_logging()


def main() -> None:
    setup_logging()
    print_banner()
    logger = logging.getLogger("fphelper")

    config = load_or_create_config(CONFIG_PATH)

    bus = EventBus()
    admin = TelegramAdmin(config, CONFIG_PATH)

    logger.info("Подключаюсь к FunPay...")
    fp_client = FunPayClient(
        config.funpay.golden_key,
        bus,
        user_agent=config.funpay.user_agent or None,
        proxy=config.funpay.proxy or None,
    )
    logger.info(f"Подключено: {fp_client.account.username} (ID {fp_client.account.id})")

    try:
        balance = fp_client.account.get_balance()
        print_profile_card(fp_client.account, balance)
    except Exception:
        logger.debug("Не удалось получить баланс для карточки профиля", exc_info=True)

    builtin = load_builtin(fp_client.account, bus, admin)
    plugins = load_plugins(fp_client.account, bus, admin)
    admin.set_plugins(builtin + plugins)

    tg_thread = threading.Thread(target=admin.run, daemon=True)
    tg_thread.start()

    admin.notify_owner(
        f"✅ FPHelper запущен.\nАккаунт: {fp_client.account.username}\n"
        f"Встроенных модулей: {len(builtin)}\nПлагинов: {len(plugins)}",
        event_type="bot_started",
    )

    try:
        fp_client.run(requests_delay=config.funpay.requests_delay)
    except KeyboardInterrupt:
        logger.info("Остановлено пользователем (Ctrl+C)")


if __name__ == "__main__":
    main()
