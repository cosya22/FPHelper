"""
Генерация одноразового кода Steam Guard (Mobile Authenticator) из shared_secret,
который лежит внутри maFile. Публично задокументированный алгоритм Steam —
TOTP-подобный, но со своим 26-символьным алфавитом и шагом в 30 секунд.
"""

import hmac
import struct
from base64 import b64decode
from hashlib import sha1
from time import time

_CHARS = "23456789BCDFGHJKMNPQRTVWXY"


def generate_code(shared_secret: str, timestamp: int | None = None) -> str:
    if timestamp is None:
        timestamp = int(time())
    time_buffer = struct.pack(">Q", timestamp // 30)
    time_hmac = hmac.new(b64decode(shared_secret), time_buffer, digestmod=sha1).digest()
    begin = time_hmac[19] & 0xF
    full_code = struct.unpack(">I", time_hmac[begin:begin + 4])[0] & 0x7FFFFFFF

    code = ""
    for _ in range(5):
        full_code, i = divmod(full_code, len(_CHARS))
        code += _CHARS[i]
    return code
