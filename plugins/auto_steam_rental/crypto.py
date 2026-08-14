"""Шифрование пароля и maFile аккаунтов Steam перед записью на диск (Fernet, ключ рядом)."""

import os

from cryptography.fernet import Fernet

DATA_DIR = "storage/plugins"
KEY_PATH = os.path.join(DATA_DIR, "auto_steam_rental.key")


def _fernet() -> Fernet:
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(KEY_PATH):
        with open(KEY_PATH, "rb") as f:
            key = f.read()
    else:
        key = Fernet.generate_key()
        with open(KEY_PATH, "wb") as f:
            f.write(key)
    return Fernet(key)


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
