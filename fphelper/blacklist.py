"""
Чёрный список покупателей — общий для всех встроенных модулей (не завязан на
конкретный плагин), поэтому живёт на уровне fphelper, а не внутри одного модуля.
Хранится напрямую в JSON-файле, как config.py хранит config.json.
"""

import json
import os

BLACKLIST_PATH = "storage/builtin/blacklist.json"

RESTRICTIONS = {
    "no_delivery": "🚫 Не выдавать товар",
    "no_commands": "🚫 Не отвечать на команды",
    "no_message_notify": "🔕 Не увед. о новых сообщениях",
    "no_order_notify": "🔕 Не увед. о новых заказах",
    "no_command_notify": "🔕 Не увед. о полученных командах",
}


def _load() -> dict:
    if not os.path.exists(BLACKLIST_PATH):
        return {"users": [], "restrictions": {k: False for k in RESTRICTIONS}}
    with open(BLACKLIST_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("users", [])
    data.setdefault("restrictions", {})
    for key in RESTRICTIONS:
        data["restrictions"].setdefault(key, False)
    return data


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(BLACKLIST_PATH), exist_ok=True)
    tmp_path = f"{BLACKLIST_PATH}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, BLACKLIST_PATH)


def list_users() -> list[str]:
    return _load()["users"]


def is_blacklisted(username: str | None) -> bool:
    if not username:
        return False
    return username.lower() in {u.lower() for u in _load()["users"]}


def add_user(username: str) -> bool:
    data = _load()
    if any(u.lower() == username.lower() for u in data["users"]):
        return False
    data["users"].append(username)
    _save(data)
    return True


def remove_user(username: str) -> bool:
    data = _load()
    before = len(data["users"])
    data["users"] = [u for u in data["users"] if u.lower() != username.lower()]
    if len(data["users"]) == before:
        return False
    _save(data)
    return True


def get_restriction(key: str) -> bool:
    return _load()["restrictions"].get(key, False)


def set_restriction(key: str, value: bool) -> None:
    data = _load()
    data["restrictions"][key] = value
    _save(data)


def is_restricted(username: str | None, key: str) -> bool:
    """Заблокирован ли конкретный пользователь по конкретному правилу (и он в ЧС, и правило включено)."""
    return is_blacklisted(username) and get_restriction(key)
