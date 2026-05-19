"""持仓交易记录 API 路由：CRUD + 汇总计算 + 定投计划。"""

from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..config import US_INDEXES
from ..database import get_session
from ..models import InvestmentPlan, Transaction, User
from ..schemas import (
    InvestmentPlanCreate,
    InvestmentPlanOut,
    PortfolioSummary,
    PositionSummary,
    TransactionCreate,
    TransactionMarker,
    TransactionOut,
)
from ..services.exchange_rate import get_exchange_rate
from ..services.market_data import fetch_index_data_async, get_index_name

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
    df = await fetch_index_data_async(req.symbol, start, end, "1d")
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
        df = await fetch_index_data_async(symbol, start, end, "1d")
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


# ---- 定投计划 ----

def _calc_missed_dates(
    plan: InvestmentPlan, today: date
) -> list[date]:
    """计算计划从 last_executed 次日至 today 之间应执行的日期列表。"""
    start = (plan.last_executed + timedelta(days=1)) if plan.last_executed else plan.created_at.date()
    if start > today:
        return []
    dates: list[date] = []
    if plan.frequency == "weekly" and plan.day_of_week is not None:
        cursor = start
        while cursor <= today:
            if cursor.weekday() == plan.day_of_week:
                dates.append(cursor)
            cursor += timedelta(days=1)
    elif plan.frequency == "monthly" and plan.day_of_month is not None:
        cursor = start
        while cursor <= today:
            if cursor.day == plan.day_of_month:
                dates.append(cursor)
            cursor += timedelta(days=1)
    return dates


async def _create_transaction_for_plan(
    symbol: str,
    amount_cny: Decimal,
    trade_date: date,
    user_id: int,
    session: AsyncSession,
) -> Transaction | None:
    """为定投计划创建一笔买入交易。返回 None 表示该日期已存在记录（幂等跳过）。"""
    # 检查幂等：同用户同symbol同日期是否已有 buy
    result = await session.execute(
        select(Transaction).where(
            and_(
                Transaction.user_id == user_id,
                Transaction.symbol == symbol,
                Transaction.trade_date == trade_date,
            )
        )
    )
    if result.scalar_one_or_none():
        return None

    trade_date_str = trade_date.strftime("%Y-%m-%d")
    start = (trade_date - timedelta(days=7)).strftime("%Y-%m-%d")
    end = (trade_date + timedelta(days=1)).strftime("%Y-%m-%d")
    df = await fetch_index_data_async(symbol, start, end, "1d")
    if df.empty:
        return None

    df.index = df.index.tz_localize(None) if df.index.tz else df.index
    mask = df.index.date <= trade_date
    if mask.any():
        close_price = Decimal(str(round(float(df[mask]["close"].iloc[-1]), 2)))
    else:
        close_price = Decimal(str(round(float(df["close"].iloc[0]), 2)))

    rate = Decimal(str(round(await get_exchange_rate(), 4)))
    usd_eq = Decimal(str(round(float(amount_cny) / float(rate), 2)))
    shares = Decimal(str(round(_calc_shares(amount_cny, rate, close_price), 6)))

    tx = Transaction(
        user_id=user_id,
        symbol=symbol,
        direction="buy",
        trade_date=trade_date,
        amount_cny=amount_cny,
        close_price_usd=close_price,
        exchange_rate=rate,
        usd_equivalent=usd_eq,
        shares=shares,
    )
    session.add(tx)
    return tx


@router.get("/plans", response_model=list[InvestmentPlanOut])
async def list_plans(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """列出当前用户所有定投计划。"""
    result = await session.execute(
        select(InvestmentPlan).where(InvestmentPlan.user_id == user.id)
    )
    return result.scalars().all()


@router.post("/plans", response_model=InvestmentPlanOut)
async def create_plan(
    req: InvestmentPlanCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """新增定投计划。"""
    if req.symbol not in US_INDEXES.values():
        raise HTTPException(status_code=400, detail=f"不支持的指数: {req.symbol}")
    if req.frequency not in ("weekly", "monthly"):
        raise HTTPException(status_code=400, detail="frequency 必须为 weekly 或 monthly")
    if req.frequency == "weekly" and (req.day_of_week is None or req.day_of_week < 0 or req.day_of_week > 6):
        raise HTTPException(status_code=400, detail="weekly 需要 day_of_week (0=周一..6=周日)")
    if req.frequency == "monthly" and (req.day_of_month is None or req.day_of_month < 1 or req.day_of_month > 28):
        raise HTTPException(status_code=400, detail="monthly 需要 day_of_month (1-28)")
    if req.amount_cny <= 0:
        raise HTTPException(status_code=400, detail="金额必须大于 0")

    plan = InvestmentPlan(
        user_id=user.id,
        symbol=req.symbol,
        amount_cny=req.amount_cny,
        frequency=req.frequency,
        day_of_week=req.day_of_week,
        day_of_month=req.day_of_month,
        enabled=True,
    )
    session.add(plan)
    await session.commit()
    await session.refresh(plan)
    return plan


@router.put("/plans/{plan_id}", response_model=InvestmentPlanOut)
async def update_plan(
    plan_id: int,
    req: InvestmentPlanCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """更新定投计划。"""
    result = await session.execute(
        select(InvestmentPlan).where(
            and_(InvestmentPlan.id == plan_id, InvestmentPlan.user_id == user.id)
        )
    )
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在或无权修改")

    plan.symbol = req.symbol
    plan.amount_cny = req.amount_cny
    plan.frequency = req.frequency
    plan.day_of_week = req.day_of_week
    plan.day_of_month = req.day_of_month
    await session.commit()
    await session.refresh(plan)
    return plan


@router.patch("/plans/{plan_id}/toggle")
async def toggle_plan(
    plan_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """切换定投计划的启用/暂停状态。"""
    result = await session.execute(
        select(InvestmentPlan).where(
            and_(InvestmentPlan.id == plan_id, InvestmentPlan.user_id == user.id)
        )
    )
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在或无权修改")
    plan.enabled = not plan.enabled
    await session.commit()
    return {"detail": "已切换", "enabled": plan.enabled}


@router.delete("/plans/{plan_id}")
async def delete_plan(
    plan_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """删除定投计划。"""
    result = await session.execute(
        select(InvestmentPlan).where(
            and_(InvestmentPlan.id == plan_id, InvestmentPlan.user_id == user.id)
        )
    )
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在或无权删除")
    await session.delete(plan)
    await session.commit()
    return {"detail": "已删除"}


@router.post("/plans/execute")
async def execute_plans(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """执行所有启用的定投计划，创建到期的买入交易。"""
    result = await session.execute(
        select(InvestmentPlan).where(
            and_(InvestmentPlan.user_id == user.id, InvestmentPlan.enabled == True)
        )
    )
    plans = result.scalars().all()

    today = date.today()
    created: list[dict] = []

    for plan in plans:
        missed = _calc_missed_dates(plan, today)
        for trade_date in missed:
            tx = await _create_transaction_for_plan(
                plan.symbol, plan.amount_cny, trade_date, user.id, session
            )
            if tx:
                created.append({
                    "symbol": plan.symbol,
                    "trade_date": trade_date.isoformat(),
                    "amount_cny": float(plan.amount_cny),
                })
        plan.last_executed = today

    await session.commit()
    return {"executed": len(created), "transactions": created}


# ---- 交易标记（图表叠加） ----

@router.get("/transactions/markers", response_model=list[TransactionMarker])
async def get_transaction_markers(
    symbol: str,
    start_date: str,
    end_date: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """获取指定指数和时间范围内的交易标记（用于图表叠加）。"""
    result = await session.execute(
        select(Transaction).where(
            and_(
                Transaction.user_id == user.id,
                Transaction.symbol == symbol,
                Transaction.trade_date >= date.fromisoformat(start_date),
                Transaction.trade_date <= date.fromisoformat(end_date),
            )
        ).order_by(Transaction.trade_date.asc())
    )
    txs = result.scalars().all()
    return [
        TransactionMarker(
            trade_date=tx.trade_date.isoformat(),
            direction=tx.direction,
            amount_cny=tx.amount_cny,
            close_price_usd=tx.close_price_usd,
        )
        for tx in txs
    ]
