"""Тонкая обёртка над pyfragment (неофициальная библиотека для Fragment.com) для покупки Stars."""

import asyncio

from pyfragment import FragmentClient


async def _purchase(seed: str, api_key: str, cookies: dict, username: str, amount: int):
    async with FragmentClient(seed=seed, api_key=api_key, cookies=cookies) as client:
        return await client.purchase_stars(username, amount)


def purchase_stars_sync(seed: str, api_key: str, cookies: dict, username: str, amount: int):
    """Синхронная обёртка — воркер плагина синхронный, а pyfragment асинхронный."""
    return asyncio.run(_purchase(seed, api_key, cookies, username, amount))
