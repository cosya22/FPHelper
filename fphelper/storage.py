import json
import os
import threading


class PluginStorage:
    """Простое потокобезопасное JSON-хранилище, изолированное на один плагин."""

    def __init__(self, path: str):
        self._path = path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def _read(self) -> dict:
        if not os.path.exists(self._path):
            return {}
        with open(self._path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write(self, data: dict) -> None:
        tmp_path = f"{self._path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self._path)

    def get(self, key: str, default=None):
        with self._lock:
            return self._read().get(key, default)

    def set(self, key: str, value) -> None:
        with self._lock:
            data = self._read()
            data[key] = value
            self._write(data)

    def update(self, mapping: dict) -> None:
        with self._lock:
            data = self._read()
            data.update(mapping)
            self._write(data)

    def all(self) -> dict:
        with self._lock:
            return self._read()
