"""RAG 对话 API 路由，处理用户对海龟交易法则的提问。使用 RAG v3 流水线。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.rag_v3 import ask_question_v3


class ChatRequest(BaseModel):
    message: str
    history: list[dict] | None = None  # [{role: "user"/"assistant", content: "..."}]


class ChatResponse(BaseModel):
    answer: str
    sources: list[dict]
    # v3 额外字段
    is_precise: bool | None = None          # 问题是否被判定为精确
    search_queries: list[str] | None = None  # 实际使用的检索查询列表
    avg_distance: float | None = None        # 检索结果的平均向量距离


router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """向海龟交易法则知识库提问。

    接收用户消息和历史对话，使用 RAG v3（智能评估 + 选择性扩展 + 多查询融合检索）
    返回基于《海龟交易法则》原书的回答及引用来源。
    """
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    try:
        result = ask_question_v3(req.message, req.history or [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG 服务出错: {str(e)}")

    return ChatResponse(
        answer=result["answer"],
        sources=result["sources"],
        is_precise=result.get("is_precise"),
        search_queries=result.get("search_queries"),
        avg_distance=result.get("avg_distance"),
    )
