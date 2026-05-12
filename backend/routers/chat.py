"""RAG 对话 API 路由，处理用户对海龟交易法则的提问。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.rag import ask_question


class ChatRequest(BaseModel):
    message: str
    history: list[dict] | None = None  # [{role: "user"/"assistant", content: "..."}]


class ChatResponse(BaseModel):
    answer: str
    sources: list[dict]


router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """向海龟交易法则知识库提问。

    接收用户消息和历史对话，返回基于《海龟交易法则》原书的回答及引用来源。
    """
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    try:
        result = ask_question(req.message, req.history or [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG 服务出错: {str(e)}")

    return ChatResponse(answer=result["answer"], sources=result["sources"])
