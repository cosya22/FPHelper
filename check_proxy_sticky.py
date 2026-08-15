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

# ЗАМЕНИТЕ строку ниже на свой РЕАЛЬНЫЙ прокси из настроек бота (config.json ->
# funpay -> proxy), например: "http://user400874:9bryvj@89.106.202.24:1326"
# Если оставить как есть — скрипт откажется запускаться.
PROXY = "http://user:pass@host:port"

if PROXY == "http://user:pass@host:port":
    raise SystemExit(
        "❌ Вы не заменили PROXY на свой реальный прокси — откройте файл в блокноте, "
        "впишите в строку PROXY = \"...\" ваш адрес из config.json и запустите снова."
    )

if "://" not in PROXY:
    PROXY = f"http://{PROXY}"  # можно вписывать и без схемы, как в самом боте

proxies = {"http": PROXY, "https": PROXY}

ips = []
errors = 0
for i in range(5):
    try:
        r = requests.get("https://api.ipify.org?format=json", proxies=proxies, timeout=10)
        ip = r.json()["ip"]
    except Exception as e:
        ip = f"ОШИБКА: {e}"
        errors += 1
    ips.append(ip)
    print(f"Запрос {i + 1}: {ip}")

print()
if errors == len(ips):
    print("❌ Все 5 запросов упали с ошибкой — прокси не подключается вообще.")
    print("Проверьте логин/пароль/адрес/порт — они должны совпадать с тем, что в config.json.")
elif errors:
    print(f"⚠️ {errors} из 5 запросов упали с ошибкой — прокси нестабилен.")
else:
    unique = set(ips)
    if len(unique) == 1:
        print("✅ Прокси ЛИПКИЙ — IP не меняется. Дело не в ротации прокси, причина в чём-то другом.")
    else:
        print(f"⚠️ Прокси РОТИРУЮЩИЙ — увидено {len(unique)} разных IP из 5 запросов.")
        print("Это, скорее всего, и есть причина ошибки FunPay — сессия привязывается к IP,")
        print("а следующий запрос уходит уже с другого адреса.")
