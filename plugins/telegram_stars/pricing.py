"""
Котировка цены: курс TON/RUB с CoinGecko (публичный API, без ключа) и цена звёзд
на Fragment. Цена звёзд получается тем же запросом, с которого начинается покупка
(searchStarsRecipient -> updateStarsBuyState -> initBuyStarsRequest), но без
последнего шага (getBuyStarsLink + сама транзакция) — то есть без реальной оплаты.
"""

import asyncio
import random

import requests
from pyfragment import FragmentClient
from pyfragment.core.constants import STARS_PAGE
from pyfragment.domains.payments import parse_required_payment_amount
from pyfragment.enums import PaymentMethod

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
PROBE_USERNAME = "durov"  # существующий аккаунт, нужен только чтобы получить котировку
REFERENCE_AMOUNT = 50  # минимальное кол-во звёзд на Fragment — по нему считаем цену за штуку


def get_ton_rub_rate(timeout: float = 10.0) -> float:
    resp = requests.get(COINGECKO_URL, params={"ids": "the-open-network", "vs_currencies": "rub"}, timeout=timeout)
    resp.raise_for_status()
    return float(resp.json()["the-open-network"]["rub"])


async def _quote_stars_price_ton(client: FragmentClient, amount: int) -> float:
    result = await client.call("searchStarsRecipient", {"query": PROBE_USERNAME, "quantity": ""}, page_url=STARS_PAGE)
    recipient = result.get("found", {}).get("recipient")
    if not recipient:
        raise RuntimeError("Fragment не вернул получателя для котировки цены")

    await client.call(
        "updateStarsBuyState",
        {"mode": "new", "lv": "false", "dh": str(random.randint(100_000_000, 2_147_483_647))},
        page_url=STARS_PAGE,
    )
    result = await client.call(
        "initBuyStarsRequest",
        {"recipient": recipient, "quantity": amount, "payment_method": PaymentMethod.GRAM.value},
        page_url=STARS_PAGE,
    )
    price = parse_required_payment_amount(result)
    if price is None:
        raise RuntimeError("Fragment не вернул цену")
    return price


async def _quote(seed: str, api_key: str, cookies: dict):
    async with FragmentClient(seed=seed, api_key=api_key, cookies=cookies) as client:
        ton_price = await _quote_stars_price_ton(client, REFERENCE_AMOUNT)
        wallet = await client.get_wallet()
        return ton_price / REFERENCE_AMOUNT, wallet.gram_balance


def quote_price_per_star_and_balance_sync(seed: str, api_key: str, cookies: dict):
    """Возвращает (цена 1 звезды в TON, баланс кошелька в TON)."""
    return asyncio.run(_quote(seed, api_key, cookies))
