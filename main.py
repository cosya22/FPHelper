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


def main() -> None:
    setup_logging()
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

    builtin = load_builtin(fp_client.account, bus, admin)
    plugins = load_plugins(fp_client.account, bus, admin)
    admin.set_plugins(builtin + plugins)

    tg_thread = threading.Thread(target=admin.run, daemon=True)
    tg_thread.start()

    admin.notify_owner(
        f"✅ FPHelper запущен.\nАккаунт: {fp_client.account.username}\n"
        f"Встроенных модулей: {len(builtin)}\nПлагинов: {len(plugins)}"
    )

    try:
        fp_client.run(requests_delay=config.funpay.requests_delay)
    except KeyboardInterrupt:
        logger.info("Остановлено пользователем (Ctrl+C)")


if __name__ == "__main__":
    main()
