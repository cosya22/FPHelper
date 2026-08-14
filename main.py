import logging
import os
import sys
import threading

from fphelper.config import CONFIG_PATH, load_or_create_config
from fphelper.events import EventBus
from fphelper.funpay_client import FunPayClient
from fphelper.plugin_manager import load_plugins
from fphelper.telegram_admin import TelegramAdmin


def setup_logging() -> None:
    os.makedirs("logs", exist_ok=True)

    # На Windows консоль часто в cp1251/cp866 и падает на эмодзи в логах.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("logs/fphelper.log", encoding="utf-8"),
        ],
    )


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

    plugins = load_plugins(fp_client.account, bus, admin)
    admin.set_plugins(plugins)

    tg_thread = threading.Thread(target=admin.run, daemon=True)
    tg_thread.start()

    admin.notify_admins(
        f"✅ FPHelper запущен.\nАккаунт: {fp_client.account.username}\nПлагинов загружено: {len(plugins)}"
    )

    try:
        fp_client.run(requests_delay=config.funpay.requests_delay)
    except KeyboardInterrupt:
        logger.info("Остановлено пользователем (Ctrl+C)")


if __name__ == "__main__":
    main()
