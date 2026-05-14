"""美股指数数据 API 路由，提供指数列表和综合技术分析数据。"""

from datetime import datetime

import pandas as pd
from fastapi import APIRouter, Query, HTTPException

from ..config import US_INDEXES
from ..services.market_data import fetch_index_data, list_indexes, get_index_name
from ..services.indicators import (
    compute_bollinger,
    compute_atr,
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

    if end_date is None:
        end_date = datetime.today().strftime("%Y-%m-%d")
    if start_date is None:
        from datetime import timedelta
        start_date = (datetime.today() - timedelta(days=180)).strftime("%Y-%m-%d")

    # 获取原始数据
    df = fetch_index_data(symbol, start_date, end_date, interval)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"{symbol}: 选定时间范围内无数据，请调整日期范围")

    # 计算技术指标
    bollinger = compute_bollinger(df)
    atr_series = compute_atr(df)
    donchian = compute_donchian(df)

    # 统计指标
    # 使用 OHLC 完整四价：开盘为起点，最高/最低反映真实日内极值
    start_price = df["open"].iloc[0]
    end_price = df["close"].iloc[-1]
    max_price = df["high"].max()
    min_price = df["low"].min()
    total_return = (end_price - start_price) / start_price * 100
    amplitude = (max_price - min_price) / start_price * 100

    stats = {
        "起价": round(start_price, 2),
        "收价": round(end_price, 2),
        "最高价": round(max_price, 2),
        "最高日期": str(df["high"].idxmax().date()),
        "最低价": round(min_price, 2),
        "最低日期": str(df["low"].idxmin().date()),
        "区间涨跌幅": f"{total_return:+.2f}%",
        "区间振幅": f"{amplitude:+.2f}%",
        "当前趋势": judge_trend(df, donchian),
    }

    # 投资建议
    advice = generate_advice(df, get_index_name(symbol), stats, donchian, atr_series, bollinger)

    # 序列化 DataFrame 为 JSON
    def df_to_records(df_component) -> list[dict]:
        """将 DataFrame 或 Series 转为 {date, value} 格式的记录列表。"""
        frame = df_component if isinstance(df_component, pd.DataFrame) else pd.DataFrame({"value": df_component})
        frame = frame.copy()
        frame["date"] = [str(d.date()) if hasattr(d, "date") else str(d) for d in frame.index]
        return frame.to_dict(orient="records")

    ohlcv = df_to_records(df[["open", "high", "low", "close", "volume"]])
    boll_records = df_to_records(bollinger)
    atr_records = df_to_records(atr_series)
    dc_records = df_to_records(donchian)

    # 合并指标到按日期的结构
    dates_index: dict[str, dict] = {}
    for r in ohlcv:
        dates_index[r["date"]] = r

    for r in boll_records:
        d = r.pop("date")
        if d in dates_index:
            dates_index[d].update({k: round(v, 2) if pd.notna(v) else None for k, v in r.items() if k != "value"})

    for r in atr_records:
        d = r.pop("date")
        v = r.get("value")
        if d in dates_index and v is not None and pd.notna(v):
            dates_index[d]["atr"] = round(v, 2)

    for r in dc_records:
        d = r.pop("date")
        if d in dates_index:
            for k, v in r.items():
                if k != "value" and pd.notna(v):
                    dates_index[d][k] = round(v, 2)

    return {
        "symbol": symbol,
        "name": get_index_name(symbol),
        "data": list(dates_index.values()),
        "stats": stats,
        "advice": advice,
        "query": {"start_date": start_date, "end_date": end_date, "interval": interval or "auto"},
    }
