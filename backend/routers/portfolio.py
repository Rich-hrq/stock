"""持仓交易记录 API 路由：CRUD + 汇总计算。"""

from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..config import US_INDEXES
from ..database import get_session
from ..models import Transaction, User
from ..schemas import (
    PortfolioSummary,
    PositionSummary,
    TransactionCreate,
    TransactionOut,
)
from ..services.exchange_rate import get_exchange_rate
from ..services.market_data import fetch_index_data, get_index_name

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


def _calc_shares(amount_cny: Decimal, rate: Decimal, close_price: Decimal) -> Decimal:
    """计算持有份额：人民币金额 ÷ 汇率 ÷ 收盘价。"""
    return float(amount_cny) / float(rate) / float(close_price)


@router.post("/transactions", response_model=TransactionOut)
async def create_transaction(
    req: TransactionCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """新增一笔交易记录。

    系统自动查询当日收盘价和当前汇率，计算美元等值和持有份额。
    """
    if req.symbol not in US_INDEXES.values():
        raise HTTPException(
            status_code=400,
            detail=f"不支持的指数代码: {req.symbol}。可用: {list(US_INDEXES.values())}",
        )
    if req.direction not in ("buy", "sell"):
        raise HTTPException(status_code=400, detail="direction 必须为 buy 或 sell")
    if req.amount_cny <= 0:
        raise HTTPException(status_code=400, detail="金额必须大于 0")

    # 查询当日收盘价
    trade_date_str = req.trade_date.strftime("%Y-%m-%d")
    # 向前多取几天数据，确保非交易日也能拿到最近的收盘价
    start = (req.trade_date - timedelta(days=7)).strftime("%Y-%m-%d")
    end = (req.trade_date + timedelta(days=1)).strftime("%Y-%m-%d")
    df = fetch_index_data(req.symbol, start, end, "1d")
    if df.empty:
        raise HTTPException(status_code=404, detail=f"{req.symbol} 在 {trade_date_str} 附近无数据")

    # 找到 <= trade_date 的最近一条数据
    df.index = df.index.tz_localize(None) if df.index.tz else df.index
    mask = df.index.date <= req.trade_date
    if mask.any():
        close_price = Decimal(str(round(float(df[mask]["close"].iloc[-1]), 2)))
    else:
        close_price = Decimal(str(round(float(df["close"].iloc[0]), 2)))

    # 查询汇率
    rate = Decimal(str(round(await get_exchange_rate(), 4)))

    usd_eq = Decimal(str(round(float(req.amount_cny) / float(rate), 2)))
    shares = Decimal(str(round(_calc_shares(req.amount_cny, rate, close_price), 6)))

    tx = Transaction(
        user_id=user.id,
        symbol=req.symbol,
        direction=req.direction,
        trade_date=req.trade_date,
        amount_cny=req.amount_cny,
        close_price_usd=close_price,
        exchange_rate=rate,
        usd_equivalent=usd_eq,
        shares=shares,
    )
    session.add(tx)
    await session.commit()
    await session.refresh(tx)
    return tx


@router.get("/transactions", response_model=list[TransactionOut])
async def list_transactions(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """获取当前用户所有交易记录，按时间倒序排列。"""
    result = await session.execute(
        select(Transaction)
        .where(Transaction.user_id == user.id)
        .order_by(Transaction.trade_date.desc(), Transaction.id.desc())
    )
    return result.scalars().all()


@router.delete("/transactions/{tx_id}")
async def delete_transaction(
    tx_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """删除指定交易记录（需验证归属权）。"""
    result = await session.execute(
        select(Transaction).where(Transaction.id == tx_id, Transaction.user_id == user.id)
    )
    tx = result.scalar_one_or_none()
    if not tx:
        raise HTTPException(status_code=404, detail="交易记录不存在或无权删除")

    await session.delete(tx)
    await session.commit()
    return {"detail": "已删除"}


@router.get("/summary", response_model=PortfolioSummary)
async def get_summary(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """计算持仓汇总：按指数分组，使用加权平均成本法。"""
    result = await session.execute(
        select(Transaction)
        .where(Transaction.user_id == user.id)
        .order_by(Transaction.trade_date.asc(), Transaction.id.asc())
    )
    txs = result.scalars().all()

    # 按 symbol 分组计算
    groups: dict[str, list[Transaction]] = {}
    for tx in txs:
        groups.setdefault(tx.symbol, []).append(tx)

    positions: list[PositionSummary] = []
    total_realized = Decimal("0")
    total_unrealized = Decimal("0")

    current_rate = Decimal(str(round(await get_exchange_rate(), 4)))

    for symbol in US_INDEXES.values():
        tx_list = groups.get(symbol, [])
        if not tx_list:
            continue

        # 加权平均成本法
        total_shares = Decimal("0")
        total_cost_cny = Decimal("0")
        realized_pnl = Decimal("0")

        for tx in tx_list:
            if tx.direction == "buy":
                total_shares += tx.shares
                total_cost_cny += tx.amount_cny
            else:  # sell
                if total_shares > 0:
                    avg_cost = total_cost_cny / total_shares
                    realized_pnl += tx.amount_cny - avg_cost * tx.shares
                    total_shares -= tx.shares
                    total_cost_cny = avg_cost * total_shares

        if total_shares <= 0:
            total_shares = Decimal("0")
            total_cost_cny = Decimal("0")

        # 获取当前收盘价
        today = date.today()
        start = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        end = (today + timedelta(days=1)).strftime("%Y-%m-%d")
        df = fetch_index_data(symbol, start, end, "1d")
        if not df.empty:
            current_price = Decimal(str(round(float(df["close"].iloc[-1]), 2)))
        else:
            current_price = Decimal("0")

        avg_cost = total_cost_cny / total_shares if total_shares > 0 else Decimal("0")
        liq_value = total_shares * current_price * current_rate if total_shares > 0 else Decimal("0")
        unrealized = liq_value - total_cost_cny if total_shares > 0 else Decimal("0")

        positions.append(
            PositionSummary(
                symbol=symbol,
                name=get_index_name(symbol),
                shares=total_shares,
                avg_cost_cny=Decimal(str(round(float(avg_cost), 2))),
                total_cost_cny=Decimal(str(round(float(total_cost_cny), 2))),
                realized_pnl_cny=Decimal(str(round(float(realized_pnl), 2))),
                current_price_usd=current_price,
                current_rate=current_rate,
                liquidation_value_cny=Decimal(str(round(float(liq_value), 2))),
                unrealized_pnl_cny=Decimal(str(round(float(unrealized), 2))),
                total_pnl_cny=Decimal(str(round(float(realized_pnl + unrealized), 2))),
            )
        )
        total_realized += realized_pnl
        total_unrealized += unrealized

    return PortfolioSummary(
        positions=positions,
        total_realized_pnl_cny=Decimal(str(round(float(total_realized), 2))),
        total_unrealized_pnl_cny=Decimal(str(round(float(total_unrealized), 2))),
        total_pnl_cny=Decimal(str(round(float(total_realized + total_unrealized), 2))),
    )
