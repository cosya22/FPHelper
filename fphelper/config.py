import getpass
import json
import os
from dataclasses import asdict, dataclass

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


def run_setup_wizard(path: str = CONFIG_PATH) -> Config:
    print("\n=== Первый запуск FPHelper: настройка ===\n")
    print("Golden key — это кука вашего аккаунта FunPay (F12 -> Application -> Cookies -> golden_key).")
    golden_key = getpass.getpass("Golden key (ввод скрыт): ").strip()

    print("\nТокен Telegram-бота получите у @BotFather командой /newbot.")
    token = getpass.getpass("Токен Telegram-бота (ввод скрыт): ").strip()

    print("\nВаш Telegram ID можно узнать у @userinfobot.")
    while True:
        owner_raw = input("Ваш Telegram ID: ").strip()
        if owner_raw.isdigit():
            break
        print("Нужно ввести число. Попробуйте снова.")

    print("\nПрокси для FunPay (необязательно, вида http://user:pass@host:port). Enter — пропустить.")
    proxy = input("Прокси: ").strip()

    config = Config(
        funpay=FunPayConfig(golden_key=golden_key, proxy=proxy),
        telegram=TelegramConfig(token=token, owner_id=int(owner_raw)),
    )
    save_config(config, path)
    print(f"\nКонфиг сохранён в {path}. Его не нужно никому передавать — там ваши секреты.\n")
    return config


def load_or_create_config(path: str = CONFIG_PATH) -> Config:
    config = load_config(path)
    if config is None:
        config = run_setup_wizard(path)
    return config
