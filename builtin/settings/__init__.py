"""
Настройки соединения прямо из Telegram — сейчас только прокси для FunPay.
Golden key и токен Telegram-бота тут не меняются намеренно: их правка на лету
может оборвать уже работающее соединение, безопаснее переустановить конфиг
(удалить config.json и перезапустить бота).

Изменение прокси применяется только после перезапуска бота — соединение
с FunPay устанавливается один раз при старте.
"""

from urllib.parse import urlparse

from fphelper import PluginInfo
from fphelper.config import CONFIG_PATH, load_config, save_config

INFO = PluginInfo(
    name="Settings",
    version="1.0.0",
    description="Настройка прокси для FunPay через Telegram, без пересоздания config.json.",
    author="you",
)

SECTION = "⚙️ Настройки"


def setup(ctx):
    def proxy_status_text():
        config = load_config(CONFIG_PATH)
        proxy = config.funpay.proxy if config else ""
        if not proxy:
            return "Прокси: выкл."
        parsed = urlparse(proxy)
        host = parsed.hostname or "?"
        port = parsed.port or "?"
        auth = " (с логином/паролем)" if parsed.username else ""
        return f"Прокси: {host}:{port}{auth}"

    @ctx.telegram.menu_item(SECTION, "🌐 Прокси", "settings:proxy_ask")
    def cbq_proxy(call):
        def on_proxy(msg):
            text = msg.text.strip()
            config = load_config(CONFIG_PATH)
            if config is None:
                ctx.telegram.bot.send_message(msg.chat.id, "❌ Не удалось прочитать config.json.")
                return

            if text == "-":
                config.funpay.proxy = ""
                save_config(config, CONFIG_PATH)
                ctx.telegram.bot.send_message(
                    msg.chat.id, "✅ Прокси убран. Перезапустите бота, чтобы это применилось."
                )
                return

            proxy = text
            if "://" not in proxy:
                proxy = f"http://{proxy}"  # провайдеры часто дают адрес без схемы
            parsed = urlparse(proxy)
            if parsed.scheme not in ("http", "https", "socks4", "socks5") or not parsed.hostname:
                ctx.telegram.bot.send_message(
                    msg.chat.id,
                    "❌ Похоже, прокси в неправильном формате. Нужно host:port или "
                    "user:pass@host:port. Откройте «🌐 Прокси» ещё раз и попробуйте снова.",
                )
                return

            config.funpay.proxy = proxy
            save_config(config, CONFIG_PATH)
            ctx.telegram.bot.send_message(
                msg.chat.id, "✅ Прокси сохранён. Перезапустите бота, чтобы это применилось."
            )

        ctx.telegram.ask(
            call.message.chat.id, call.from_user.id,
            f"{proxy_status_text()}\n\n"
            f"Пришлите новый адрес прокси (host:port или user:pass@host:port), "
            f"или «-», чтобы убрать текущий.",
            on_proxy,
        )
