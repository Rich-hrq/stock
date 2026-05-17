"""美股交易时段状态计算：判断当前是否开盘，给出下次开盘/收盘时间。

支持美东时间（EST/EDT）与北京时间（CST, UTC+8）双时区显示。
周末自动判定为休市；节假日暂不处理。
"""

from datetime import datetime, time, timedelta, date, timezone
from typing import Literal

# ---- 交易时段常量（美东时间）----
PRE_MARKET_START = time(4, 0)    # 04:00 ET
REGULAR_OPEN = time(9, 30)       # 09:30 ET
REGULAR_CLOSE = time(16, 0)      # 16:00 ET
AFTER_HOURS_END = time(20, 0)    # 20:00 ET

CN_OFFSET = timedelta(hours=8)   # 北京时间 UTC+8

MarketStatus = Literal["pre_market", "open", "after_hours", "closed"]


def _is_dst_us(d: date) -> bool:
    """判断给定日期是否处于美国夏令时（EDT, UTC-4）。

    规则：每年 3 月第二个周日 至 11 月第一个周日。
    """
    y = d.year

    # 3 月第二个周日
    mar1 = date(y, 3, 1)
    days_to_sun = (6 - mar1.weekday()) % 7
    dst_start = mar1 + timedelta(days=days_to_sun + 7)

    # 11 月第一个周日
    nov1 = date(y, 11, 1)
    days_to_sun = (6 - nov1.weekday()) % 7
    dst_end = nov1 + timedelta(days=days_to_sun)

    return dst_start <= d < dst_end


def _et_offset(d: date) -> timedelta:
    """给定日期的美东时区偏移量。"""
    return timedelta(hours=-4) if _is_dst_us(d) else timedelta(hours=-5)


def _et_tz(d: date) -> timezone:
    """返回给定日期对应的美东时区对象（UTC offset）。"""
    return timezone(_et_offset(d))


def _now_et() -> datetime:
    """获取当前美东时间（带时区）。"""
    utc_now = datetime.now(timezone.utc)
    return utc_now.astimezone(_et_tz(utc_now.date()))


def _fmt_cn(dt: datetime, label: str = "CST") -> str:
    """将时间格式化为北京时间字符串。"""
    cn = dt.astimezone(timezone(CN_OFFSET))
    return cn.strftime(f"%Y-%m-%d %H:%M {label}")


def _fmt_et(dt: datetime, label: str = "EST") -> str:
    """将时间格式化为美东时间字符串（带夏令时标签）。"""
    tz = _et_tz(dt.date())
    et = dt.astimezone(tz)
    abbr = "EDT" if _is_dst_us(dt.date()) else "EST"
    return et.strftime(f"%Y-%m-%d %H:%M {abbr}")


def _next_trading_day(d: date) -> date:
    """返回 d 之后的下一个交易日（跳过周末）。"""
    nxt = d + timedelta(days=1)
    while nxt.weekday() >= 5:  # 周六(5) 或 周日(6)
        nxt += timedelta(days=1)
    return nxt


def _is_weekend(d: date) -> bool:
    """判断是否为周末。"""
    return d.weekday() >= 5


def get_market_status() -> dict:
    """计算当前美股市场状态，返回双时区信息。"""

    utc_now = datetime.now(timezone.utc)
    now_et = _now_et()
    et_date = now_et.date()
    et_time = now_et.time()

    # ---- 周末直接判定为休市 ----
    if _is_weekend(et_date):
        next_open_date = _next_trading_day(et_date)
        next_open_et = datetime.combine(next_open_date, REGULAR_OPEN, tzinfo=_et_tz(next_open_date))
        next_close_et = datetime.combine(next_open_date, REGULAR_CLOSE, tzinfo=_et_tz(next_open_date))

        return {
            "status": "closed",
            "status_text": "周末休市",
            "status_text_en": "Weekend (Closed)",
            "current_et": _fmt_et(now_et),
            "current_cn": _fmt_cn(now_et),
            "next_event": "open",
            "next_event_time_et": _fmt_et(next_open_et),
            "next_event_time_cn": _fmt_cn(next_open_et),
            "next_event_label": "开盘",
            "next_event_label_en": "Market Open",
        }

    # ---- 交易日内部时段判断 ----
    if et_time < PRE_MARKET_START:
        # 0:00 - 4:00 → 休市，等当天盘前
        status: MarketStatus = "closed"
        status_text = "已收盘"
        status_text_en = "Market Closed"
        next_open_et = datetime.combine(et_date, REGULAR_OPEN, tzinfo=_et_tz(et_date))
        next_close_et = datetime.combine(et_date, REGULAR_CLOSE, tzinfo=_et_tz(et_date))
        next_event = "open"
        next_event_label = "开盘"
        next_event_label_en = "Market Open"

    elif et_time < REGULAR_OPEN:
        # 4:00 - 9:30 → 盘前
        status = "pre_market"
        status_text = "盘前交易"
        status_text_en = "Pre-Market"
        next_open_et = datetime.combine(et_date, REGULAR_OPEN, tzinfo=_et_tz(et_date))
        next_close_et = datetime.combine(et_date, REGULAR_CLOSE, tzinfo=_et_tz(et_date))
        next_event = "open"
        next_event_label = "开盘"
        next_event_label_en = "Market Open"

    elif et_time < REGULAR_CLOSE:
        # 9:30 - 16:00 → 交易中
        status = "open"
        status_text = "开盘中"
        status_text_en = "Market Open"
        next_open_et = None  # 已经开盘
        next_close_et = datetime.combine(et_date, REGULAR_CLOSE, tzinfo=_et_tz(et_date))
        next_event = "close"
        next_event_label = "收盘"
        next_event_label_en = "Market Close"

    elif et_time < AFTER_HOURS_END:
        # 16:00 - 20:00 → 盘后
        status = "after_hours"
        status_text = "盘后交易"
        status_text_en = "After-Hours"
        next_trade_date = _next_trading_day(et_date)
        next_open_et = datetime.combine(next_trade_date, REGULAR_OPEN, tzinfo=_et_tz(next_trade_date))
        next_close_et = datetime.combine(next_trade_date, REGULAR_CLOSE, tzinfo=_et_tz(next_trade_date))
        next_event = "open"
        next_event_label = "开盘"
        next_event_label_en = "Market Open"

    else:
        # 20:00 - 24:00 → 休市，等下一个交易日
        status = "closed"
        status_text = "已收盘"
        status_text_en = "Market Closed"
        next_trade_date = _next_trading_day(et_date)
        next_open_et = datetime.combine(next_trade_date, REGULAR_OPEN, tzinfo=_et_tz(next_trade_date))
        next_close_et = datetime.combine(next_trade_date, REGULAR_CLOSE, tzinfo=_et_tz(next_trade_date))
        next_event = "open"
        next_event_label = "开盘"
        next_event_label_en = "Market Open"

    result = {
        "status": status,
        "status_text": status_text,
        "status_text_en": status_text_en,
        "current_et": _fmt_et(now_et),
        "current_cn": _fmt_cn(now_et),
        "next_event": next_event,
        "next_event_time_et": _fmt_et(next_close_et if next_event == "close" else next_open_et),
        "next_event_time_cn": _fmt_cn(next_close_et if next_event == "close" else next_open_et),
        "next_event_label": next_event_label,
        "next_event_label_en": next_event_label_en,
    }

    return result
