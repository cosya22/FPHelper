"""
Смена пароля Steam через официальный визард восстановления доступа
(help.steampowered.com/wizard/...) — тот же путь, что и "Я забыл пароль"
на сайте, но подтверждается через мобильный Steam Guard (identity_secret
из maFile) вместо письма на почту.

Основано на разборе открытой (MIT) реализации того же флоу —
github.com/Kewanmov/FunPay-Cardinal-Auto-Steam-Rent — но переписано
самостоятельно поверх асинхронного клиента pysteamauth и архитектуры
FPHelper, а не скопировано.

⚠️ Это не документированный Valve API, а последовательность внутренних
AJAX-запросов страницы восстановления. У меня нет реального аккаунта
Steam, чтобы проверить это вживую — код может содержать ошибки, а Steam
может в любой момент поменять флоу и сломать его. Плагин на этот случай
всегда подстрахован: при любой ошибке владельцу приходит уведомление
сменить пароль вручную, аккаунт не остаётся в неопределённом состоянии.
"""

import asyncio
import base64
import json
import re
import secrets
import string
import urllib.parse
from dataclasses import dataclass

import rsa
from pysteamauth.auth import Steam

HELP = "https://help.steampowered.com"


class SteamPasswordChangeError(Exception):
    pass


@dataclass
class _WizardParams:
    s: int
    account: int
    reset: int
    issueid: int
    lost: int = 0


def _generate_password(length: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _parse_json(text: str, context: str) -> dict:
    text = (text or "").strip()
    if not text:
        raise SteamPasswordChangeError(f"{context}: пустой ответ от Steam")
    if text.startswith("<"):
        raise SteamPasswordChangeError(
            f"{context}: Steam вернул страницу вместо JSON — возможно, для этого аккаунта "
            "требуется подтверждение по почте (IP бота не доверенный)."
        )
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise SteamPasswordChangeError(f"{context}: не удалось разобрать ответ Steam ({e})")


async def _get_wizard_params(steam: Steam) -> _WizardParams:
    text = await steam.request(f"{HELP}/wizard/HelpChangePassword?redir=store/account/")
    found = {}
    for key in ("s", "account", "reset", "issueid"):
        m = re.search(rf"[?&]{key}=(\d+)", text)
        if m:
            found[key] = int(m.group(1))
    if not all(k in found for k in ("s", "account", "reset", "issueid")):
        raise SteamPasswordChangeError("Не удалось получить параметры визарда восстановления пароля")
    return _WizardParams(**found)


async def _confirm_via_mobile(steam: Steam, params: _WizardParams) -> None:
    for _ in range(20):
        server_time = await steam.get_server_time()
        conf_key = steam.get_confirmation_hash(server_time, "conf")
        getlist_url = (
            "https://steamcommunity.com/mobileconf/getlist"
            f"?p={urllib.parse.quote(steam.device_id)}&a={steam.steamid}"
            f"&k={urllib.parse.quote(conf_key)}&t={server_time}&m=android&tag=conf"
        )
        data = _parse_json(await steam.request(getlist_url), "getlist")
        confs = data.get("conf", []) if data.get("success") else []

        target = next((c for c in confs if str(c.get("creator_id", "")) == str(params.s)), None)
        if target is None:
            for c in confs:
                blob = f"{c.get('summary', '')} {c.get('type_name', '')}".lower()
                if any(x in blob for x in ("recovery", "password", "account")):
                    target = c
                    break
        if target is None and len(confs) == 1:
            target = confs[0]
        if target is None:
            await asyncio.sleep(3)
            continue

        server_time2 = await steam.get_server_time()
        allow_key = steam.get_confirmation_hash(server_time2, "allow")
        ajaxop_url = (
            "https://steamcommunity.com/mobileconf/ajaxop"
            f"?p={urllib.parse.quote(steam.device_id)}&a={steam.steamid}"
            f"&k={urllib.parse.quote(allow_key)}&t={server_time2}&m=android&tag=allow&op=allow"
            f"&cid={target['id']}&ck={target['nonce']}"
        )
        result = _parse_json(await steam.request(ajaxop_url), "ajaxop")
        if result.get("success"):
            return
        raise SteamPasswordChangeError("Steam отклонил мобильное подтверждение смены пароля")

    raise SteamPasswordChangeError(
        "Не дождались подтверждения Steam Guard. Возможно, IP бота не доверенный для "
        "этого аккаунта — один раз войдите в аккаунт с этого сервера и подтвердите по почте."
    )


async def _help_post(steam: Steam, endpoint: str, data: dict) -> dict:
    text = await steam.request(f"{HELP}{endpoint}", method="POST", data=data)
    return _parse_json(text, endpoint)


async def _get_rsa_key(steam: Steam, login: str) -> dict:
    r = await _help_post(steam, "/en/login/getrsakey/", {"username": login})
    if not r.get("publickey_mod"):
        raise SteamPasswordChangeError("Steam не вернул ключ RSA для шифрования пароля")
    return r


def _encrypt(password: str, mod: str, exp: str) -> str:
    key = rsa.PublicKey(n=int(mod, 16), e=int(exp, 16))
    return base64.b64encode(rsa.encrypt(password.encode("ascii"), key)).decode()


async def _change(login: str, current_password: str, shared_secret: str,
                   identity_secret: str, device_id: str, steamid: int) -> str:
    steam = Steam(
        login=login, password=current_password, steamid=steamid,
        shared_secret=shared_secret, identity_secret=identity_secret, device_id=device_id,
    )
    await steam.login_to_steam()

    params = await _get_wizard_params(steam)
    await _confirm_via_mobile(steam, params)

    await _help_post(steam, "/en/wizard/AjaxPollAccountRecoveryConfirmation", {
        "wizard_ajax": "1", "s": params.s, "reset": params.reset,
        "lost": params.lost, "method": "8", "issueid": params.issueid, "gamepad": "0",
    })
    await _help_post(steam, "/en/wizard/AjaxAccountRecoveryGetNextStep", {
        "wizard_ajax": "1", "s": params.s, "account": params.account,
        "reset": params.reset, "issueid": params.issueid, "lost": "2",
    })

    key = await _get_rsa_key(steam, login)
    enc_old = _encrypt(current_password, key["publickey_mod"], key["publickey_exp"])
    await _help_post(steam, "/en/wizard/AjaxAccountRecoveryVerifyPassword/", {
        "s": params.s, "lost": "2", "reset": "1", "password": enc_old, "rsatimestamp": key["timestamp"],
    })

    new_password = _generate_password()
    avail = await _help_post(steam, "/en/wizard/AjaxCheckPasswordAvailable/", {
        "wizard_ajax": "1", "password": new_password,
    })
    if not avail.get("available"):
        raise SteamPasswordChangeError("Сгенерированный пароль отклонён Steam, попробуйте ещё раз")

    key2 = await _get_rsa_key(steam, login)
    enc_new = _encrypt(new_password, key2["publickey_mod"], key2["publickey_exp"])
    result = await _help_post(steam, "/en/wizard/AjaxAccountRecoveryChangePassword/", {
        "wizard_ajax": "1", "s": params.s, "account": params.account,
        "password": enc_new, "rsatimestamp": key2["timestamp"],
    })
    if not result.get("success") and not result.get("hash"):
        raise SteamPasswordChangeError(f"Steam не подтвердил смену пароля: {result}")

    return new_password


def change_password_sync(login: str, current_password: str, shared_secret: str,
                          identity_secret: str, device_id: str, steamid: int) -> str:
    """Меняет пароль аккаунта Steam, возвращает новый. Кидает SteamPasswordChangeError при сбое."""
    return asyncio.run(_change(login, current_password, shared_secret, identity_secret, device_id, steamid))
