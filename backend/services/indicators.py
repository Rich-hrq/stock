"""海龟交易法则技术指标计算模块。

基于《海龟交易法则》原书规则，计算并展示趋势跟踪所需的核心指标：
- 布林带（Bollinger Bands, 20/2）
- 平均真实波幅（ATR / N 值, 20日）
- 唐奇安通道（Donchian Channel, 20日/55日）
"""

import pandas as pd

from config import BOLLINGER_PERIOD, BOLLINGER_STD, ATR_PERIOD, DONCHIAN_ENTRY, DONCHIAN_STOP


def compute_bollinger(df: pd.DataFrame, period: int = BOLLINGER_PERIOD, num_std: float = BOLLINGER_STD) -> pd.DataFrame:
    """计算布林带。

    中轨 = MA(period), 上轨 = 中轨 + num_std * σ, 下轨 = 中轨 - num_std * σ

    Returns:
        DataFrame 含 boll_upper, boll_middle, boll_lower 三列
    """
    close = df["close"]
    middle = close.rolling(window=period).mean()
    std = close.rolling(window=period).std()
    return pd.DataFrame({
        "boll_upper": middle + num_std * std,
        "boll_middle": middle,
        "boll_lower": middle - num_std * std,
    }, index=df.index)


def compute_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    """计算平均真实波幅 (ATR)，海龟交易法则中称为 N 值。

    True Range = max(high-low, |high-prev_close|, |low-prev_close|)
    ATR = TR 的 period 日移动平均

    海龟使用 N 值进行头寸规模计算：头寸 = 账户权益的1% / N
    """
    high, low = df["high"], df["low"]
    prev_close = df["close"].shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = true_range.rolling(window=period).mean()
    return atr


def compute_donchian(df: pd.DataFrame) -> pd.DataFrame:
    """计算唐奇安通道。

    突破策略：
    - 系统1（短期）：20日高点入场，10日低点出场
    - 系统2（长期）：55日高点入场，20日低点出场
    """
    high, low = df["high"], df["low"]
    return pd.DataFrame({
        "dc_high_20": high.rolling(window=DONCHIAN_ENTRY).max(),
        "dc_low_10": low.rolling(window=10).min(),
        "dc_high_55": high.rolling(window=DONCHIAN_STOP).max(),
        "dc_low_20": low.rolling(window=DONCHIAN_ENTRY).min(),
    }, index=df.index)


def judge_trend(df: pd.DataFrame, donchian: pd.DataFrame) -> str:
    """根据唐奇安通道判断当前趋势方向。

    逻辑（基于海龟交易法则）：
    - 价格 > 20日高点 → 上升趋势（突破做多信号）
    - 价格 < 20日低点 → 下降趋势（突破做空/平仓信号）
    - 其他 → 盘整/无明确信号
    """
    if len(df) < DONCHIAN_ENTRY:
        return "数据不足，无法判断"
    latest_close = df["close"].iloc[-1]
    dc_high = donchian["dc_high_20"].iloc[-1]
    dc_low = donchian["dc_low_20"].iloc[-1]

    if latest_close >= dc_high:
        return "上升趋势（突破20日唐奇安通道上轨，系统1做多信号）"
    elif latest_close <= dc_low:
        return "下降趋势（跌破20日唐奇安通道下轨，系统1平仓/做空信号）"
    else:
        return "盘整（价格在唐奇安通道内，无明确入场信号）"


def generate_advice(
    df: pd.DataFrame,
    name: str,
    stats: dict,
    donchian: pd.DataFrame,
    atr: pd.Series,
    bollinger: pd.DataFrame,
) -> str:
    """基于技术指标生成趋势跟踪投资建议。

    参考海龟交易法则的完整交易系统：入市、止损、退出、头寸规模。
    """
    if len(df) < DONCHIAN_ENTRY:
        return "数据不足以生成投资建议，请选择更长的时间范围。"

    latest_close = df["close"].iloc[-1]
    latest_atr = atr.dropna().iloc[-1] if not atr.dropna().empty else 0
    trend = judge_trend(df, donchian)
    bb = bollinger.dropna()

    parts = [f"【{name} 趋势跟踪建议】\n"]

    # 1. 趋势判断
    parts.append(f"当前趋势：{trend}")

    # 2. 价格在布林带中的位置
    if not bb.empty:
        upper = bb["boll_upper"].iloc[-1]
        middle = bb["boll_middle"].iloc[-1]
        lower = bb["boll_lower"].iloc[-1]
        bb_width_pct = (upper - lower) / middle * 100
        pos_in_band = (latest_close - lower) / (upper - lower) * 100 if upper != lower else 50
        parts.append(f"\n布林带(20,2)：上轨 {upper:.2f} | 中轨 {middle:.2f} | 下轨 {lower:.2f}")
        parts.append(f"带宽：{bb_width_pct:.1f}%（带宽越宽波动越大），价格位于带内 {pos_in_band:.0f}% 位置")
        if pos_in_band >= 90:
            parts.append("→ 价格接近上轨，短期可能超买")
        elif pos_in_band <= 10:
            parts.append("→ 价格接近下轨，短期可能超卖")

    # 3. ATR / N 值与止损建议
    if latest_atr > 0:
        parts.append(f"\nATR(20) / N值：{latest_atr:.2f}")
        parts.append("海龟止损规则：任何交易的风险不超过账户的2%")
        # 以 N 值为单位建议止损
        stop_loss_2n = latest_close - 2 * latest_atr
        parts.append(f"建议止损位（2N法则）：{stop_loss_2n:.2f}（当前价 - 2 × N）")

    # 4. 入市/持仓建议
    if "上升趋势" in trend:
        parts.append(f"\n入市建议：唐奇安通道系统1已发出做多信号。")
        parts.append("- 可等待价格小幅回调至20日均线附近建仓")
        parts.append(f"- 止损设置在20日低点({donchian['dc_low_20'].iloc[-1]:.2f})下方")
        parts.append("- 海龟加仓：价格每上涨0.5N，可增加一个单位头寸（最多4个单位）")
    elif "下降趋势" in trend:
        parts.append(f"\n持仓建议：趋势向下，若持有多头应考虑减仓或平仓。")
        parts.append("- 空头突破信号（系统1）：跌破20日低点可考虑做空")
        parts.append("- 多头应等待价格重新突破20日高点再入场")
    else:
        parts.append(f"\n当前处于盘整区间，建议等待突破信号。")
        parts.append("- 突破20日高点为做多信号")
        parts.append("- 跌破20日低点为做空/平仓信号")
        parts.append("- 耐心等待是海龟交易法则的重要原则")

    parts.append(f"\n区间涨跌幅：{stats['区间涨跌幅']} | 区间振幅：{stats['区间振幅']}")
    return "\n".join(parts)
