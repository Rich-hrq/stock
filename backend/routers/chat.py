"""RAG 对话 API 路由，处理用户对海龟交易法则的提问。使用 RAG v3 流水线。"""

import asyncio

from fastapi import APIRouter, HTTPException

from ..schemas import ChatRequest, ChatResponse
from ..services.rag_v3 import ask_question_v3_async


router = APIRouter(prefix="/api", tags=["chat"])

_rag_semaphore = asyncio.Semaphore(3)


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """向海龟交易法则知识库提问。

    接收用户消息和历史对话，使用 RAG v3（智能评估 + 选择性扩展 + 多查询融合检索）
    返回基于《海龟交易法则》原书的回答及引用来源。
    """
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    try:
        async with _rag_semaphore:
            result = await ask_question_v3_async(req.message, req.history or [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG 服务出错: {str(e)}")

    return ChatResponse(
        answer=result["answer"],
        sources=result["sources"],
        is_precise=result.get("is_precise"),
        search_queries=result.get("search_queries"),
        avg_distance=result.get("avg_distance"),
    )
