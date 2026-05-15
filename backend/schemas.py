"""Pydantic 请求/响应模型，定义所有 API 接口的数据格式。"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


# ---- 对话 (chat.py) ----

class ChatRequest(BaseModel):
    """RAG 对话请求"""
    message: str
    history: list[dict] | None = None  # [{role: "user"/"assistant", content: "..."}]


class ChatResponse(BaseModel):
    """RAG 对话响应"""
    answer: str
    sources: list[dict]
    # v3 额外字段
    is_precise: bool | None = None          # 问题是否被判定为精确
    search_queries: list[str] | None = None  # 实际使用的检索查询列表
    avg_distance: float | None = None        # 检索结果的平均向量距离


# ---- 预测市场 (prediction.py) ----

class PredictRequest(BaseModel):
    """Polymarket 预测市场查询请求"""
    keywords: list[str] = ["nasdaq", "^ndx", "s&p500", "dow jones"]
    limit: int = 500
    threshold: int = 100000


# ---- 新闻摘要 (guardian.py) ----

class NewsSummaryRequest(BaseModel):
    """AI 新闻摘要请求"""
    headlines: list[dict]  # [{title, link}, ...]


class NewsSummaryResponse(BaseModel):
    """AI 新闻摘要响应"""
    summary: str
    generated_at: str


# ---- 用户认证 ----

class UserCreate(BaseModel):
    """注册请求"""
    username: str
    password: str


class UserLogin(BaseModel):
    """登录请求"""
    username: str
    password: str


class TokenResponse(BaseModel):
    """登录/注册成功响应"""
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    """用户信息响应"""
    id: int
    username: str
    created_at: datetime


# ---- 持仓交易 ----

class TransactionCreate(BaseModel):
    """新增交易请求"""
    symbol: str
    direction: str  # buy / sell
    trade_date: date
    amount_cny: Decimal


class TransactionOut(BaseModel):
    """交易记录响应（完整字段）"""
    id: int
    symbol: str
    direction: str
    trade_date: date
    amount_cny: Decimal
    close_price_usd: Decimal
    exchange_rate: Decimal
    usd_equivalent: Decimal
    shares: Decimal
    created_at: datetime

    class Config:
        from_attributes = True


class PositionSummary(BaseModel):
    """单只指数的持仓汇总"""
    symbol: str
    name: str
    shares: Decimal
    avg_cost_cny: Decimal
    total_cost_cny: Decimal
    realized_pnl_cny: Decimal
    current_price_usd: Decimal
    current_rate: Decimal
    liquidation_value_cny: Decimal
    unrealized_pnl_cny: Decimal
    total_pnl_cny: Decimal


class PortfolioSummary(BaseModel):
    """整体持仓汇总"""
    positions: list[PositionSummary]
    total_realized_pnl_cny: Decimal
    total_unrealized_pnl_cny: Decimal
    total_pnl_cny: Decimal
