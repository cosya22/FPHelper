# -*- coding: utf-8 -*-
"""
Проверка: липкий ли прокси (один и тот же исходящий IP на разных запросах)
или ротирующий (IP меняется от запроса к запросу).

Впишите свой прокси ниже и запустите:
    python check_proxy_sticky.py

Если IP на всех 5 запросах ОДИНАКОВЫЙ — прокси липкий, дело не в нём.
Если IP МЕНЯЕТСЯ — вот и причина ошибки "cookie отсутствует или устарела" у FunPay.
"""
import requests

PROXY = "http://user:pass@host:port"  # <-- впишите сюда свой реальный прокси

proxies = {"http": PROXY, "https": PROXY}

ips = []
for i in range(5):
    try:
        r = requests.get("https://api.ipify.org?format=json", proxies=proxies, timeout=10)
        ip = r.json()["ip"]
    except Exception as e:
        ip = f"ОШИБКА: {e}"
    ips.append(ip)
    print(f"Запрос {i + 1}: {ip}")

unique = set(ips)
print()
if len(unique) == 1:
    print("✅ Прокси ЛИПКИЙ — IP не меняется. Дело не в ротации прокси, причина в чём-то другом.")
else:
    print(f"⚠️ Прокси РОТИРУЮЩИЙ — увидено {len(unique)} разных IP из 5 запросов.")
    print("Это, скорее всего, и есть причина ошибки FunPay — сессия привязывается к IP,")
    print("а следующий запрос уходит уже с другого адреса.")
