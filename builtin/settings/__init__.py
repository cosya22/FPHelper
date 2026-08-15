"""
Настройки соединения прямо из Telegram — сейчас только прокси для FunPay.
Golden key и токен Telegram-бота тут не меняются намеренно: их правка на лету
может оборвать уже работающее соединение, безопаснее переустановить конфиг
(удалить config.json и перезапустить бота).

Изменение прокси применяется только после перезапуска бота — соединение
с FunPay устанавливается один раз при старте.
"""

import json
import os
from urllib.parse import urlparse

from fphelper import PluginInfo
from fphelper.config import CONFIG_PATH, Config, load_config, save_config

INFO = PluginInfo(
    name="Settings",
    version="1.2.0",
    description="Настройка прокси и экспорт/импорт конфига для FunPay через Telegram.",
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

    @ctx.telegram.menu_item(SECTION, "🌐 Прокси", "settings:proxy_ask", group="СОЕДИНЕНИЕ")
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

    @ctx.telegram.menu_item(SECTION, "⬇️ Выгрузить конфиг", "settings:export", group="КОНФИГИ")
    def cbq_export(call):
        if not os.path.exists(CONFIG_PATH):
            ctx.telegram.bot.send_message(call.message.chat.id, "❌ config.json не найден.")
            return
        with open(CONFIG_PATH, "rb") as f:
            ctx.telegram.bot.send_document(
                call.message.chat.id, f, visible_file_name="config.json",
                caption="Ваш config.json — там golden key и токен бота, никому не пересылайте.",
            )

    @ctx.telegram.menu_item(SECTION, "⬆️ Загрузить конфиг", "settings:import_ask", group="КОНФИГИ")
    def cbq_import_ask(call):
        def on_file(msg):
            document = getattr(msg, "document", None)
            if not document:
                ctx.telegram.bot.send_message(msg.chat.id, "Это не похоже на файл. Пришлите config.json (или /cancel).")
                return
            try:
                file_info = ctx.telegram.bot.get_file(document.file_id)
                raw = ctx.telegram.bot.download_file(file_info.file_path)
                data = json.loads(raw.decode("utf-8"))
                Config.from_dict(data)  # только валидация формата
            except Exception as e:
                ctx.telegram.bot.send_message(msg.chat.id, f"❌ Файл не похож на корректный config.json: {e}")
                return

            with open(CONFIG_PATH, "wb") as f:
                f.write(raw)
            ctx.telegram.bot.send_message(
                msg.chat.id, "✅ Конфиг загружен. Перезапустите бота, чтобы применить."
            )

        ctx.telegram.ask(call.message.chat.id, call.from_user.id, "Пришлите файл config.json.", on_file)
