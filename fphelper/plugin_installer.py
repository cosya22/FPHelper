"""
Безопасная распаковка присланного .zip с плагином в plugins/. Защищает от zip-slip
(файлов вне целевой папки через "../" или абсолютные пути), ограничивает размер
архива и распакованного содержимого, ищет папку плагина внутри архива на случай,
если она обёрнута в лишний внешний каталог (частый случай при скачивании с GitHub).
"""

import io
import os
import re
import shutil
import uuid
import zipfile

PLUGINS_DIR = "plugins"
MAX_ZIP_SIZE = 20 * 1024 * 1024
MAX_UNPACKED_SIZE = 100 * 1024 * 1024
MAX_NESTING = 5
JUNK_NAMES = {"__MACOSX", "__pycache__", ".git", ".idea", ".vscode", ".DS_Store", "Thumbs.db"}


class PluginInstallError(Exception):
    """Ошибка установки плагина с текстом, готовым к показу пользователю."""


def _member_parts(name: str) -> list[str] | None:
    name = (name or "").replace("\\", "/")
    if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        return None
    parts = [p for p in name.split("/") if p and p != "."]
    if not parts or any(p == ".." for p in parts):
        return None
    if any(p in JUNK_NAMES or p.startswith("._") for p in parts):
        return None
    return parts


def _extract_zip(data: bytes, dest: str) -> None:
    if len(data) > MAX_ZIP_SIZE:
        raise PluginInstallError(f"Архив слишком большой (максимум {MAX_ZIP_SIZE // 1024 // 1024} МБ).")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise PluginInstallError("Файл повреждён или это не .zip.")

    total = 0
    files = 0
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            parts = _member_parts(info.filename)
            if not parts:
                continue
            target = os.path.join(dest, *parts)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with archive.open(info) as src, open(target, "wb") as out:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_UNPACKED_SIZE:
                        raise PluginInstallError(
                            f"Распакованный архив слишком большой (максимум {MAX_UNPACKED_SIZE // 1024 // 1024} МБ)."
                        )
                    out.write(chunk)
            files += 1

    if not files:
        raise PluginInstallError("В архиве нет файлов.")


def _find_plugin_root(path: str, depth: int = 0) -> str | None:
    if os.path.isfile(os.path.join(path, "__init__.py")):
        return path
    entries = [os.path.join(path, n) for n in os.listdir(path) if os.path.isdir(os.path.join(path, n))]
    if len(entries) == 1 and depth < MAX_NESTING:
        return _find_plugin_root(entries[0], depth + 1)
    return None


def _safe_name(raw: str) -> str:
    name = re.sub(r"[^0-9A-Za-z_]+", "_", raw or "").strip("_")
    if not name:
        name = f"plugin_{uuid.uuid4().hex[:8]}"
    if name[0].isdigit():
        name = f"plugin_{name}"
    return name


def install_plugin_from_zip(data: bytes, suggested_name: str) -> str:
    """
    Распаковывает архив плагина в plugins/<name>/.

    :param data: содержимое .zip файла.
    :param suggested_name: имя файла архива — используется для имени папки плагина.
    :return: имя установленной папки плагина в plugins/.
    :raises PluginInstallError: если архив битый, слишком большой или в нём нет плагина.
    """
    os.makedirs(PLUGINS_DIR, exist_ok=True)
    stage = os.path.join(PLUGINS_DIR, f".stage_{uuid.uuid4().hex[:8]}")
    os.makedirs(stage, exist_ok=True)

    try:
        _extract_zip(data, stage)
        root = _find_plugin_root(stage)
        if root is None:
            raise PluginInstallError(
                "В архиве не найдена папка плагина с файлом __init__.py."
            )

        name = _safe_name(os.path.splitext(suggested_name)[0])
        dest = os.path.join(PLUGINS_DIR, name)
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.move(root, dest)
        return name
    finally:
        if os.path.exists(stage):
            shutil.rmtree(stage, ignore_errors=True)
