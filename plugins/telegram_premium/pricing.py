"""
Котировка цены: курс TON/RUB с CoinGecko (публичный API, без ключа) и цена Premium
на Fragment за конкретное число месяцев. Цена получается тем же запросом, с которого
начинается покупка (searchPremiumGiftRecipient -> updatePremiumState ->
initGiftPremiumRequest), но без последнего шага (getGiftPremiumLink + сама
транзакция) — то есть без реальной оплаты.
"""

import asyncio
import random

import requests
from pyfragment import FragmentClient
from pyfragment.core.constants import PREMIUM_PAGE
from pyfragment.domains.payments import parse_required_payment_amount
from pyfragment.enums import PaymentMethod

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
PROBE_USERNAME = "durov"  # существующий аккаунт, нужен только чтобы получить котировку


def get_ton_rub_rate(timeout: float = 10.0) -> float:
    resp = requests.get(COINGECKO_URL, params={"ids": "the-open-network", "vs_currencies": "rub"}, timeout=timeout)
    resp.raise_for_status()
    return float(resp.json()["the-open-network"]["rub"])


async def _quote_premium_price_ton(client: FragmentClient, months: int) -> float:
    result = await client.call("searchPremiumGiftRecipient", {"query": PROBE_USERNAME, "months": months}, page_url=PREMIUM_PAGE)
    recipient = result.get("found", {}).get("recipient")
    if not recipient:
        raise RuntimeError("Fragment не вернул получателя для котировки цены")

    await client.call(
        "updatePremiumState",
        {"mode": "new", "lv": "false", "dh": str(random.randint(100_000_000, 2_147_483_647))},
        page_url=PREMIUM_PAGE,
    )
    result = await client.call(
        "initGiftPremiumRequest",
        {"recipient": recipient, "months": months, "payment_method": PaymentMethod.GRAM.value},
        page_url=PREMIUM_PAGE,
    )
    price = parse_required_payment_amount(result)
    if price is None:
        raise RuntimeError("Fragment не вернул цену")
    return price


async def _quote(seed: str, api_key: str, cookies: dict, months: int):
    async with FragmentClient(seed=seed, api_key=api_key, cookies=cookies) as client:
        ton_price = await _quote_premium_price_ton(client, months)
        wallet = await client.get_wallet()
        return ton_price, wallet.gram_balance


def quote_premium_price_and_balance_sync(seed: str, api_key: str, cookies: dict, months: int):
    """Возвращает (цена Premium на months месяцев в TON, баланс кошелька в TON)."""
    return asyncio.run(_quote(seed, api_key, cookies, months))
