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

BUILTIN_DIR = "builtin"
PLUGINS_DIR = "plugins"
STORAGE_DIR = "storage"


@dataclass
class LoadedPlugin:
    dir_name: str
    info: PluginInfo
    builtin: bool = False


def _load_from_dir(account: Account, bus: EventBus, admin: TelegramAdmin,
                    package_dir: str, builtin: bool) -> list[LoadedPlugin]:
    """Импортирует каждую папку package_dir/<name>/ с __init__.py и вызывает её setup(ctx)."""
    os.makedirs(package_dir, exist_ok=True)
    init_path = os.path.join(package_dir, "__init__.py")
    if not os.path.exists(init_path):
        open(init_path, "w").close()

    storage_subdir = "builtin" if builtin else "plugins"
    kind_label = "встроенный модуль" if builtin else "плагин"

    loaded: list[LoadedPlugin] = []
    for name in sorted(os.listdir(package_dir)):
        module_path = os.path.join(package_dir, name)
        if not os.path.isdir(module_path) or not os.path.isfile(os.path.join(module_path, "__init__.py")):
            continue
        try:
            module = importlib.import_module(f"{package_dir}.{name}")
            setup_fn = getattr(module, "setup", None)
            if setup_fn is None:
                logger.warning(f"{kind_label.capitalize()} «{name}» не содержит функцию setup(ctx) — пропущен")
                continue
            info = getattr(module, "INFO", None) or PluginInfo(name=name)

            ctx = PluginContext(
                account=account,
                events=PluginEvents(bus),
                telegram=PluginTelegram(admin),
                storage=PluginStorage(os.path.join(STORAGE_DIR, storage_subdir, f"{name}.json")),
                logger=logging.getLogger(f"fphelper.{storage_subdir}.{name}"),
                notify_admins=admin.notify_admins,
            )
            setup_fn(ctx)
            loaded.append(LoadedPlugin(dir_name=name, info=info, builtin=builtin))
            logger.info(f"Загружен {kind_label}: {info.name} v{info.version}")
        except Exception:
            logger.exception(f"Ошибка при загрузке {kind_label}а «{name}»")

    return loaded


def load_builtin(account: Account, bus: EventBus, admin: TelegramAdmin) -> list[LoadedPlugin]:
    """Загружает встроенные модули бота (ядро функциональности) из builtin/."""
    return _load_from_dir(account, bus, admin, BUILTIN_DIR, builtin=True)


def load_plugins(account: Account, bus: EventBus, admin: TelegramAdmin) -> list[LoadedPlugin]:
    """Загружает сторонние/пользовательские плагины из plugins/."""
    return _load_from_dir(account, bus, admin, PLUGINS_DIR, builtin=False)
