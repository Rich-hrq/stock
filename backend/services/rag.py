"""海龟交易法则 RAG 问答服务。

使用 LangGraph 构建检索增强生成流水线，基于《海龟交易法则》PDF 原书回答问题。

流水线流程：
    用户提问 → 嵌入检索（ChromaDB） → 上下文组装 → Claude 生成回答
"""

from typing import Annotated, TypedDict

import chromadb
from langchain_anthropic import ChatAnthropic
from sentence_transformers import SentenceTransformer
from langgraph.graph import StateGraph, END

from ..config import (
    CHROMA_DB_DIR,
    TOP_K_RETRIEVAL,
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
)


# LangGraph 状态定义
class RAGState(TypedDict):
    question: str
    history: list[dict]  # [{role: "user"/"assistant", content: "..."}]
    context: list[str]
    sources: list[dict]
    answer: str


# ---- 全局单例 ----
_embed_model: SentenceTransformer | None = None
_chroma_collection: chromadb.Collection | None = None
_llm: ChatAnthropic | None = None


def _get_embed_model() -> SentenceTransformer:
    """懒加载嵌入模型（首次加载较慢，后续调用复用）。"""
    global _embed_model
    if _embed_model is None:
        _embed_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    return _embed_model


def _get_collection() -> chromadb.Collection:
    """懒加载 ChromaDB collection。"""
    global _chroma_collection
    if _chroma_collection is None:
        client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
        _chroma_collection = client.get_collection("turtle_trading")
    return _chroma_collection


def _get_llm() -> ChatAnthropic:
    """懒加载 LLM 实例。"""
    global _llm
    if _llm is None:
        _llm = ChatAnthropic(
            model=ANTHROPIC_MODEL,
            api_key=ANTHROPIC_API_KEY,
            temperature=0.3,  # 低温度以确保回答忠实于原书
            max_tokens=2048,
        )
    return _llm


# ---- LangGraph 节点 ----

RETRIEVAL_PROMPT = """你是海龟交易法则的专家助手。请仅根据以下从《海龟交易法则》书中检索到的原文内容回答用户问题。

规则：
1. 严格基于提供的原文内容回答，不要编造或使用外部知识
2. 如果原文中没有足够信息，请明确告知用户"书中未提及此内容"
3. 回答时尽量引用原文所在的页码
4. 回答要清晰易懂，因为用户正在学习股票交易知识
5. 使用中文回答

以下是从书中检索到的相关内容：
---
{context}
---

历史对话：
{history}

用户问题：{question}
"""


def retrieve_node(state: RAGState) -> dict:
    """检索节点：将用户问题嵌入后从 ChromaDB 检索最相关的文本块。"""
    embed_model = _get_embed_model()
    collection = _get_collection()

    query_embedding = embed_model.encode(state["question"]).tolist()
    results = collection.query(query_embeddings=[query_embedding], n_results=TOP_K_RETRIEVAL)

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]

    context = []
    sources = []
    for doc, meta in zip(docs, metas):
        context.append(doc)
        sources.append({"page": meta.get("page", "未知"), "text": doc[:200] + "..."})

    return {"context": context, "sources": sources}


def generate_node(state: RAGState) -> dict:
    """生成节点：将检索到的上下文 + 用户问题发送给 Claude 生成回答。"""
    llm = _get_llm()

    context_str = "\n\n---\n\n".join(
        f"[页码 {s['page']}] {c}" for s, c in zip(state["sources"], state["context"])
    )

    # 格式化历史对话
    history_str = ""
    if state.get("history"):
        for msg in state["history"]:
            role = "用户" if msg["role"] == "user" else "助手"
            history_str += f"{role}: {msg['content']}\n"
    if not history_str:
        history_str = "（无历史对话）"

    prompt = RETRIEVAL_PROMPT.format(
        context=context_str,
        history=history_str,
        question=state["question"],
    )

    response = llm.invoke(prompt)
    return {"answer": response.content}


# ---- 构建状态图 ----

def build_rag_graph() -> StateGraph:
    """构建并编译 LangGraph RAG 流水线。"""
    graph = StateGraph(RAGState)

    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate", generate_node)

    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)

    return graph.compile()


# 模块级编译实例，避免每次请求重新编译
rag_app = build_rag_graph()


def ask_question(question: str, history: list[dict] | None = None) -> dict:
    """RAG 问答的统一入口。

    Args:
        question: 用户的问题
        history: 历史对话记录 [{role, content}, ...]

    Returns:
        {"answer": str, "sources": [{"page": int, "text": str}, ...]}
    """
    initial_state: RAGState = {
        "question": question,
        "history": history or [],
        "context": [],
        "sources": [],
        "answer": "",
    }
    result = rag_app.invoke(initial_state)
    return {"answer": result["answer"], "sources": result["sources"]}
