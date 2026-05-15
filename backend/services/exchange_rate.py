"""汇率查询服务，从 open.er-api.com 获取实时 USD/CNY 汇率。"""

import time

import httpx

from ..config import EXCHANGE_RATE_URL, HTTP_PROXY

# 简单缓存：(rate, timestamp)
_cache: tuple[float, float] = (0.0, 0.0)
_CACHE_TTL = 3600  # 1 小时


async def get_exchange_rate() -> float:
    """获取当前 USD/CNY 汇率，带 1 小时内存缓存。

    Returns:
        1 美元对应的人民币数量，如 7.21
    """
    global _cache
    rate, ts = _cache
    now = time.time()

    if rate > 0 and now - ts < _CACHE_TTL:
        return rate

    proxy = HTTP_PROXY if HTTP_PROXY else None
    async with httpx.AsyncClient(proxy=proxy, timeout=10) as client:
        resp = await client.get(EXCHANGE_RATE_URL)
        resp.raise_for_status()
        data = resp.json()
        rate = float(data["rates"]["CNY"])

    _cache = (rate, now)
    return rate
