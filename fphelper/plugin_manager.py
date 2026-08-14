import importlib
import logging
import os
from dataclasses import dataclass

from FunPayAPI.account import Account

from .context import PluginContext, PluginEvents, PluginInfo, PluginTelegram
from .events import EventBus
from .storage import PluginStorage
from .telegram_admin import TelegramAdmin

logger = logging.getLogger("fphelper.plugins")

PLUGINS_DIR = "plugins"
STORAGE_DIR = "storage"


@dataclass
class LoadedPlugin:
    dir_name: str
    info: PluginInfo


def load_plugins(account: Account, bus: EventBus, admin: TelegramAdmin) -> list[LoadedPlugin]:
    """Импортирует каждую папку plugins/<name>/ с __init__.py и вызывает её setup(ctx)."""
    os.makedirs(PLUGINS_DIR, exist_ok=True)
    init_path = os.path.join(PLUGINS_DIR, "__init__.py")
    if not os.path.exists(init_path):
        open(init_path, "w").close()

    loaded: list[LoadedPlugin] = []
    for name in sorted(os.listdir(PLUGINS_DIR)):
        plugin_path = os.path.join(PLUGINS_DIR, name)
        if not os.path.isdir(plugin_path) or not os.path.isfile(os.path.join(plugin_path, "__init__.py")):
            continue
        try:
            module = importlib.import_module(f"{PLUGINS_DIR}.{name}")
            setup_fn = getattr(module, "setup", None)
            if setup_fn is None:
                logger.warning(f"Плагин «{name}» не содержит функцию setup(ctx) — пропущен")
                continue
            info = getattr(module, "INFO", None) or PluginInfo(name=name)

            ctx = PluginContext(
                account=account,
                events=PluginEvents(bus),
                telegram=PluginTelegram(admin),
                storage=PluginStorage(os.path.join(STORAGE_DIR, f"{name}.json")),
                logger=logging.getLogger(f"fphelper.plugins.{name}"),
                notify_admins=admin.notify_admins,
            )
            setup_fn(ctx)
            loaded.append(LoadedPlugin(dir_name=name, info=info))
            logger.info(f"Загружен плагин: {info.name} v{info.version}")
        except Exception:
            logger.exception(f"Ошибка при загрузке плагина «{name}»")

    return loaded
