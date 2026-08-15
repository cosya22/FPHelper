import json
import os
from dataclasses import asdict, dataclass
from urllib.parse import urlparse

from colorama import Fore, Style, init as colorama_init

colorama_init()

CONFIG_PATH = "config.json"


@dataclass
class FunPayConfig:
    golden_key: str
    user_agent: str = ""
    requests_delay: float = 6.0
    proxy: str = ""  # например http://user:pass@host:port, пусто — без прокси


@dataclass
class TelegramConfig:
    token: str
    owner_id: int = 0


@dataclass
class Config:
    funpay: FunPayConfig
    telegram: TelegramConfig

    def to_dict(self) -> dict:
        return {"funpay": asdict(self.funpay), "telegram": asdict(self.telegram)}

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        return cls(
            funpay=FunPayConfig(**data["funpay"]),
            telegram=TelegramConfig(**data["telegram"]),
        )


def load_config(path: str = CONFIG_PATH) -> Config | None:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return Config.from_dict(json.load(f))


def save_config(config: Config, path: str = CONFIG_PATH) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, ensure_ascii=False, indent=2)


def _header(text: str) -> None:
    print(f"\n{Style.BRIGHT}{Fore.CYAN}=== {text} ==={Style.RESET_ALL}\n")


def _hint(text: str) -> None:
    print(f"{Fore.YELLOW}{text}{Style.RESET_ALL}")


def _error(text: str) -> None:
    print(f"{Fore.RED}{text}{Style.RESET_ALL}")


def _success(text: str) -> None:
    print(f"{Fore.GREEN}{text}{Style.RESET_ALL}")


def _prompt(text: str) -> str:
    return input(f"{Style.BRIGHT}{Fore.WHITE}{text}{Style.RESET_ALL}")


def run_setup_wizard(path: str = CONFIG_PATH) -> Config:
    _header("Первый запуск FPHelper: настройка")
    _hint("Golden key — это кука вашего аккаунта FunPay (F12 -> Application -> Cookies -> golden_key).")
    while True:
        golden_key = _prompt("Golden key: ").strip()
        if golden_key:
            break
        _error("Golden key не может быть пустым. Попробуйте снова.")

    print()
    _hint("Токен Telegram-бота получите у @BotFather командой /newbot.")
    _hint("Токен выглядит так: 123456789:AAExampleTokenTextGoesHereABCDEF")
    while True:
        token = _prompt("Токен Telegram-бота: ").strip()
        if ":" in token:
            break
        _error("Похоже на неполный токен (должен содержать ':'). Проверьте, что скопировали его целиком, и попробуйте снова.")

    print()
    _hint("Ваш Telegram ID можно узнать у @userinfobot.")
    while True:
        owner_raw = _prompt("Ваш Telegram ID: ").strip()
        if owner_raw.isdigit():
            break
        _error("Нужно ввести число. Попробуйте снова.")

    print()
    _hint("Прокси для FunPay (необязательно, вида http://user:pass@host:port). Enter — пропустить.")
    while True:
        proxy = _prompt("Прокси: ").strip()
        if not proxy:
            break
        parsed = urlparse(proxy)
        if parsed.scheme in ("http", "https", "socks4", "socks5") and parsed.hostname:
            break
        _error(
            "Похоже, прокси в неправильном формате. Нужно вида http://host:port или "
            "http://user:pass@host:port (со схемой в начале). Попробуйте снова, либо Enter — пропустить."
        )

    config = Config(
        funpay=FunPayConfig(golden_key=golden_key, proxy=proxy),
        telegram=TelegramConfig(token=token, owner_id=int(owner_raw)),
    )
    save_config(config, path)
    _success(f"\nКонфиг сохранён в {path}. Его не нужно никому передавать — там ваши секреты.\n")
    return config


def load_or_create_config(path: str = CONFIG_PATH) -> Config:
    config = load_config(path)
    if config is None:
        config = run_setup_wizard(path)
    return config
