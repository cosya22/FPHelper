"""Тонкая обёртка над pyfragment (неофициальная библиотека для Fragment.com) для дарения Premium."""

import asyncio

from pyfragment import FragmentClient


async def _gift(seed: str, api_key: str, cookies: dict, username: str, months: int):
    async with FragmentClient(seed=seed, api_key=api_key, cookies=cookies) as client:
        return await client.purchase_premium(username, months)


def gift_premium_sync(seed: str, api_key: str, cookies: dict, username: str, months: int):
    """Синхронная обёртка — воркер плагина синхронный, а pyfragment асинхронный."""
    return asyncio.run(_gift(seed, api_key, cookies, username, months))
