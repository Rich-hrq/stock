"""美股指数数据获取服务，封装 yfinance 并添加文件缓存层。"""

import asyncio
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timedelta
from functools import lru_cache

import pandas as pd
import yfinance as yf

from ..config import (
    HTTP_PROXY,
    US_INDEXES,
    MARKET_DATA_CACHE_DIR,
    MARKET_DATA_CACHE_ENABLED,
    MARKET_DATA_CACHE_MAX_AGE_DAYS,
)

logger = logging.getLogger(__name__)


def _set_proxy() -> None:
    """为 yfinance 设置网络代理（国内环境需要）。"""
    if HTTP_PROXY and "all_proxy" not in os.environ:
        os.environ["all_proxy"] = HTTP_PROXY


def auto_interval(start_date: str, end_date: str) -> str:
    """根据时间跨度自动选择合适的数据粒度。

    同日查询用小时线以展示日内细节，跨日查询用日线以确保 OHLC 与 Yahoo Finance 一致。
    （yfinance 1h 和 1d 间隔的首根开盘价可能不一致，日线数据与网页端对齐）
    """
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    days = (end - start).days

    if days <= 0:
        return "1h"    # 同日：日内细节
    return "1d"         # 跨日：日线，与 Yahoo Finance 对齐


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


async def fetch_index_data_async(
    symbol: str,
    start_date: str,
    end_date: str,
    interval: str | None = None,
) -> pd.DataFrame:
    """fetch_index_data 的异步包装，带文件缓存层。

    缓存策略：同日相同参数的请求只调用一次 yfinance API，
    后续直接从本地 Pickle 文件读取。次日自动过期。
    """
    if interval is None:
        interval = auto_interval(start_date, end_date)

    # 尝试读取缓存
    if MARKET_DATA_CACHE_ENABLED:
        cached = _read_cache(symbol, start_date, end_date, interval)
        if cached is not None:
            return cached

    # 缓存未命中或缓存关闭，走 API
    df = await asyncio.to_thread(fetch_index_data, symbol, start_date, end_date, interval)

    # 写入缓存（仅非空数据）
    if MARKET_DATA_CACHE_ENABLED and not df.empty:
        _write_cache(symbol, start_date, end_date, interval, df)
        _cleanup_old_cache()

    return df


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


# ---- 文件缓存 ----

def _cache_key(symbol: str, start_date: str, end_date: str, interval: str) -> str:
    """根据查询参数生成缓存文件名的唯一标识（MD5 前 16 位）。"""
    raw = f"{symbol}|{start_date}|{end_date}|{interval}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _read_cache(symbol: str, start_date: str, end_date: str, interval: str) -> pd.DataFrame | None:
    """读取缓存。

    命中条件：缓存文件存在 + 元数据存在 + 参数匹配 + 缓存日期为今天。
    任何异常（损坏、版本不兼容）均返回 None，由调用方回退到 API。
    """
    try:
        key = _cache_key(symbol, start_date, end_date, interval)
        pkl_path = MARKET_DATA_CACHE_DIR / f"{key}.pkl"
        meta_path = MARKET_DATA_CACHE_DIR / f"{key}.meta.json"

        if not pkl_path.exists() or not meta_path.exists():
            return None

        # 校验元数据
        meta = json.loads(meta_path.read_text())
        if (
            meta.get("symbol") != symbol
            or meta.get("start_date") != start_date
            or meta.get("end_date") != end_date
            or meta.get("interval") != interval
        ):
            return None

        # 检查是否今天缓存
        cached_at = datetime.fromisoformat(meta["cached_at"])
        if cached_at.date() != datetime.today().date():
            return None

        df = pd.read_pickle(pkl_path)
        if df.empty:
            return None
        return df

    except Exception:
        logger.warning("读取市场数据缓存失败，回退到 API", exc_info=True)
        return None


def _write_cache(symbol: str, start_date: str, end_date: str, interval: str, df: pd.DataFrame) -> None:
    """写入缓存（原子操作：先写临时文件再重命名）。"""
    try:
        MARKET_DATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        key = _cache_key(symbol, start_date, end_date, interval)
        pkl_path = MARKET_DATA_CACHE_DIR / f"{key}.pkl"
        meta_path = MARKET_DATA_CACHE_DIR / f"{key}.meta.json"
        tmp_pkl = MARKET_DATA_CACHE_DIR / f"{key}.pkl.tmp"
        tmp_meta = MARKET_DATA_CACHE_DIR / f"{key}.meta.json.tmp"

        # 写入临时文件
        df.to_pickle(tmp_pkl)
        meta = {
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "interval": interval,
            "cached_at": datetime.now().isoformat(),
        }
        tmp_meta.write_text(json.dumps(meta, ensure_ascii=False))

        # 原子替换
        os.replace(tmp_pkl, pkl_path)
        os.replace(tmp_meta, meta_path)

    except Exception:
        logger.warning("写入市场数据缓存失败", exc_info=True)
        # 清理可能残留的临时文件
        for tmp in [tmp_pkl, tmp_meta]:
            if tmp.exists():
                tmp.unlink(missing_ok=True)


def _cleanup_old_cache() -> None:
    """清理超过 MAX_AGE_DAYS 天的缓存文件。"""
    try:
        if not MARKET_DATA_CACHE_DIR.exists():
            return
        now = time.time()
        cutoff = now - MARKET_DATA_CACHE_MAX_AGE_DAYS * 86400
        for f in MARKET_DATA_CACHE_DIR.iterdir():
            if f.is_file():
                try:
                    if f.stat().st_mtime < cutoff:
                        f.unlink()
                except OSError:
                    pass
    except Exception:
        logger.warning("缓存清理失败", exc_info=True)
