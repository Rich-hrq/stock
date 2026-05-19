"""美股指数数据 API 路由，提供指数列表和综合技术分析数据（含均线/布林带/唐奇安通道/ATR）。"""

import asyncio
from datetime import datetime

import pandas as pd
from fastapi import APIRouter, Query, HTTPException

from ..config import US_INDEXES
from ..services.market_data import fetch_index_data_async, list_indexes, get_index_name
from ..services.indicators import (
    compute_bollinger,
    compute_atr,
    compute_ma,
    compute_donchian,
    generate_advice,
    judge_trend,
)

router = APIRouter(prefix="/api/indices", tags=["indices"])


@router.get("")
async def get_indices():
    """返回所有可用美股指数列表。"""
    return {"indices": list_indexes()}


@router.get("/{symbol}/analysis")
async def get_index_analysis(
    symbol: str,
    start_date: str | None = Query(None, description="起始日期 YYYY-MM-DD，默认距今180天"),
    end_date: str | None = Query(None, description="截止日期 YYYY-MM-DD，默认今天"),
    interval: str | None = Query(None, description="数据粒度 1h/1d/1wk，默认自动选择"),
):
    """获取单个指数的完整技术分析数据。

    返回 OHLCV 数据、布林带、唐奇安通道、ATR、统计指标和投资建议。
    """
    if symbol not in US_INDEXES.values():
        raise HTTPException(status_code=400, detail=f"不支持的指数代码: {symbol}。可用: {list(US_INDEXES.values())}")

    from datetime import timedelta

    if end_date is None:
        end_date = datetime.today().strftime("%Y-%m-%d")
    if start_date is None:
        start_date = (datetime.today() - timedelta(days=180)).strftime("%Y-%m-%d")

    # 获取原始数据
    df = await fetch_index_data_async(symbol, start_date, end_date, interval)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"{symbol}: 选定时间范围内无数据，请调整日期范围")

    # 获取前日收盘价日线数据（与 Yahoo Finance 对齐）
    prev_start_dt = datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=7)
    df_daily = await fetch_index_data_async(symbol, prev_start_dt.strftime("%Y-%m-%d"), end_date, "1d")

    # 技术指标计算和统计在线程池中执行（pandas 密集型计算）
    index_name = get_index_name(symbol)

    def _compute_analysis():
        bollinger = compute_bollinger(df)
        atr_series = compute_atr(df)
        donchian = compute_donchian(df)
        ma5 = compute_ma(df, 5)
        ma10 = compute_ma(df, 10)

        start_price = df["open"].iloc[0]
        end_price = df["close"].iloc[-1]
        max_price = df["high"].max()
        min_price = df["low"].min()
        total_return = (end_price - start_price) / start_price * 100
        amplitude = (max_price - min_price) / start_price * 100

        prev_close = None
        prev_close_date = None
        if len(df_daily) >= 2:
            prev_close = round(float(df_daily["close"].iloc[-2]), 2)
            prev_close_date = str(df_daily.index[-2].date())
        daily_change = (end_price - prev_close) / prev_close * 100 if prev_close else None

        stats = {
            "起价": round(start_price, 2),
            "收价": round(end_price, 2),
            "最高价": round(max_price, 2),
            "最高日期": str(df["high"].idxmax().date()),
            "最低价": round(min_price, 2),
            "最低日期": str(df["low"].idxmin().date()),
            "区间涨跌幅": f"{total_return:+.2f}%",
            "区间振幅": f"{amplitude:+.2f}%",
            "前日收盘": prev_close,
            "日涨跌": f"{daily_change:+.2f}%" if daily_change is not None else None,
            "当前趋势": judge_trend(df, donchian),
        }

        advice = generate_advice(df, index_name, stats, donchian, atr_series, bollinger)

        def _fmt_date(idx_val) -> str:
            if hasattr(idx_val, "isoformat"):
                return idx_val.isoformat()
            return str(idx_val)

        ohlcv_records = []
        for i in range(len(df)):
            d = _fmt_date(df.index[i])
            row = df.iloc[i]
            rec = {
                "date": d,
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"],
            }
            for col in ["boll_upper", "boll_middle", "boll_lower"]:
                v = bollinger[col].iloc[i]
                rec[col] = round(float(v), 2) if pd.notna(v) else None
            v = atr_series.iloc[i]
            rec["atr"] = round(float(v), 2) if pd.notna(v) else None
            for col in ["dc_high_20", "dc_low_10", "dc_high_55", "dc_low_20"]:
                v = donchian[col].iloc[i]
                rec[col] = round(float(v), 2) if pd.notna(v) else None
            for col, series in [("ma5", ma5), ("ma10", ma10)]:
                v = series.iloc[i]
                rec[col] = round(float(v), 2) if pd.notna(v) else None
            ohlcv_records.append(rec)

        return stats, advice, ohlcv_records

    stats, advice, ohlcv_records = await asyncio.to_thread(_compute_analysis)

    return {
        "symbol": symbol,
        "name": index_name,
        "data": ohlcv_records,
        "stats": stats,
        "advice": advice,
        "query": {"start_date": start_date, "end_date": end_date, "interval": interval or "auto"},
    }
