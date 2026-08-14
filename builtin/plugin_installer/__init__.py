"""Установка новых плагинов прямо из Telegram — присылаете .zip, бот распаковывает в plugins/."""

from fphelper import PluginInfo
from fphelper.plugin_installer import PluginInstallError, install_plugin_from_zip

INFO = PluginInfo(
    name="Plugin Installer",
    version="1.0.0",
    description="Установка новых плагинов из .zip прямо через Telegram.",
    author="you",
)

SECTION = "🧩 Модули"


def setup(ctx):
    @ctx.telegram.menu_item(SECTION, "➕ Установить плагин", "plugin_installer:ask")
    def cbq_install_ask(call):
        def on_file(msg):
            document = getattr(msg, "document", None)
            if not document:
                ctx.telegram.bot.send_message(
                    msg.chat.id, "Это не похоже на файл. Пришлите .zip архив с плагином (или /cancel)."
                )
                return
            if not (document.file_name or "").lower().endswith(".zip"):
                ctx.telegram.bot.send_message(msg.chat.id, "Нужен архив в формате .zip.")
                return

            try:
                file_info = ctx.telegram.bot.get_file(document.file_id)
                data = ctx.telegram.bot.download_file(file_info.file_path)
                name = install_plugin_from_zip(data, document.file_name)
            except PluginInstallError as e:
                ctx.telegram.bot.send_message(msg.chat.id, f"❌ {e}")
                return
            except Exception as e:
                ctx.logger.exception("Не удалось установить плагин из архива")
                ctx.telegram.bot.send_message(msg.chat.id, f"❌ Не удалось установить плагин: {e}")
                return

            ctx.telegram.bot.send_message(
                msg.chat.id,
                f"✅ Плагин установлен: <code>plugins/{name}</code>.\n"
                "Перезапустите бота (run.bat), чтобы он подключился.",
            )

        ctx.telegram.ask(
            call.message.chat.id, call.from_user.id,
            "Пришлите .zip архив с плагином. Внутри должна быть папка с файлом __init__.py "
            "(можно прямо в корне архива или во вложенной папке).",
            on_file,
        )
