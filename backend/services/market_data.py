"""美股指数数据获取服务，封装 yfinance 并添加缓存层。"""

import os
from datetime import datetime, timedelta
from functools import lru_cache

import pandas as pd
import yfinance as yf

from ..config import US_INDEXES, HTTP_PROXY


def _set_proxy() -> None:
    """为 yfinance 设置网络代理（国内环境需要）。"""
    if HTTP_PROXY and "all_proxy" not in os.environ:
        os.environ["all_proxy"] = HTTP_PROXY


def auto_interval(start_date: str, end_date: str) -> str:
    """根据时间跨度自动选择合适的数据粒度。"""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    days = (end - start).days

    if days <= 1:
        return "1h"
    elif days <= 7:
        return "1h"
    else:
        return "1d"


def fetch_index_data(
    symbol: str,
    start_date: str,
    end_date: str,
    interval: str | None = None,
) -> pd.DataFrame:
    """从 yfinance 获取单个指数的 OHLCV 数据。

    Args:
        symbol: Yahoo Finance Ticker 符号（如 ^GSPC）
        start_date: 起始日期 "YYYY-MM-DD"
        end_date: 截止日期 "YYYY-MM-DD"
        interval: 数据粒度（1m, 5m, 1h, 1d, 1wk），为空则自动选择

    Returns:
        DataFrame，列名统一为小写（open, high, low, close, volume）
    """
    _set_proxy()

    if interval is None:
        interval = auto_interval(start_date, end_date)

    # yfinance 的 end 参数不包含当天，所以 +1 天
    end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
    end_adj = end_dt.strftime("%Y-%m-%d")

    raw = yf.Ticker(symbol).history(start=start_date, end=end_adj, interval=interval)

    if raw.empty:
        return pd.DataFrame()

    raw.columns = [c.lower() for c in raw.columns]
    # 确保时区无关，方便前端 JSON 序列化
    if raw.index.tz is not None:
        raw.index = raw.index.tz_localize(None)
    return raw


@lru_cache(maxsize=32)
def get_index_name(symbol: str) -> str:
    """根据 symbol 反查指数中文名称。"""
    for name, sym in US_INDEXES.items():
        if sym == symbol:
            return name
    return symbol


def list_indexes() -> list[dict]:
    """返回可用指数列表，供前端下拉菜单使用。"""
    return [{"symbol": s, "name": n} for n, s in US_INDEXES.items()]
