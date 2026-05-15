"""Pydantic 请求/响应模型，定义所有 API 接口的数据格式。"""

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
