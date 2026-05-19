"""RAG v3：智能问题评估 + 选择性扩展 + 多查询融合检索。

v1: retrieve → generate（简单直接，但口语化问题检索质量差）
v2: rewrite → retrieve → judge → 条件路由（回环复杂，改写可能降低已精确问题的检索质量）
v3: evaluate → [扩展 or 跳过] → 多查询合并检索 → generate

v3 核心改进：
    1. 先评估问题是否专业精确，避免对好问题画蛇添足
    2. 不精确时生成 2-3 个同义转述，多角度检索
    3. 合并去重多组检索结果，取最相关的 top-K
    4. 去掉 v2 的回环逻辑，减少延迟和 token 消耗
"""

import asyncio
from typing import TypedDict

import chromadb
import numpy as np
from langchain_anthropic import ChatAnthropic
from sentence_transformers import SentenceTransformer
from langgraph.graph import StateGraph, END

from ..config import (
    CHROMA_DB_DIR,
    TOP_K_RETRIEVAL,
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    ANTHROPIC_BASE_URL,
)

MAX_EXPANSIONS = 3  # 最多生成几个同义转述


# ---- 状态定义 ----
class RAGStateV3(TypedDict):
    question: str                  # 原始问题
    is_precise: bool               # 问题是否已足够精确
    search_queries: list[str]      # 用于检索的问题列表（原问题 + 扩展问题）
    history: list[dict]
    context: list[str]
    sources: list[dict]
    distances: list[float]
    avg_distance: float
    answer: str


# ---- 全局单例 ----
_embed_model_v3: SentenceTransformer | None = None
_chroma_v3: chromadb.Collection | None = None
_llm_v3: ChatAnthropic | None = None


def _get_embed_model() -> SentenceTransformer:
    global _embed_model_v3
    if _embed_model_v3 is None:
        _embed_model_v3 = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    return _embed_model_v3


def _get_collection() -> chromadb.Collection:
    global _chroma_v3
    if _chroma_v3 is None:
        client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
        _chroma_v3 = client.get_collection("turtle_trading")
    return _chroma_v3


def _get_llm() -> ChatAnthropic:
    global _llm_v3
    if _llm_v3 is None:
        kwargs = dict(
            model=ANTHROPIC_MODEL,
            api_key=ANTHROPIC_API_KEY,
            temperature=0.3,
            max_tokens=2048,
        )
        if ANTHROPIC_BASE_URL:
            kwargs["base_url"] = ANTHROPIC_BASE_URL
        _llm_v3 = ChatAnthropic(**kwargs)
    return _llm_v3


def _extract_answer(response) -> str:
    content = response.content
    if isinstance(content, list):
        return "".join(block.get("text", "") for block in content if isinstance(block, dict))
    return str(content)


# ---- Prompt 模板 ----

# 1. 评估问题是否需要扩展
EVALUATE_PROMPT = """你是搜索质量评估专家。请判断以下用户问题是否已经足够精确、专业，能直接在《海龟交易法则》书中检索到相关内容。

判断标准：
- "足够精确"：问题包含专业术语（如入市策略、ATR、N值、唐奇安通道、头寸规模、止损、突破等），或表达了清晰的查询意图
- "需要扩展"：问题过于口语化、模糊、简短（如"这个咋用""止损咋设的""他们怎么做的"），缺乏专业术语

请只回答一个字：是（足够精确）或 否（需要扩展）

用户问题：{question}

回答："""

# 2. 扩展口语化问题为多个专业表述
EXPAND_PROMPT = """你是《海龟交易法则》领域的搜索优化专家。用户的问题口语化/模糊，请将其转写为 2-3 个更专业、更精确的检索用问题。

规则：
1. 每个转写问题保留原始意图，但使用书中的专业术语
2. 不同转写应侧重不同角度（如一个侧重定义，一个侧重操作方法）
3. 每行一个问题，不要编号，不要额外解释
4. 使用中文

原始问题：{question}

转写后的问题：
"""

# 3. 生成回答（与 v1 相同）
GENERATE_PROMPT = """你是海龟交易法则的专家助手。请仅根据以下从《海龟交易法则》书中检索到的原文内容回答用户问题。

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


# ---- LangGraph 节点 ----

def evaluate_node(state: RAGStateV3) -> dict:
    """评估节点：判断用户问题是否已足够专业精确。

    精确 → 直接用原问题检索，跳过扩展
    不精确 → 进入扩展节点
    """
    llm = _get_llm()

    # 快速启发式判断：问题长度 ≥ 15 字且包含明显专业词 → 大概率已精确
    q = state["question"]
    technical_keywords = ["入市", "头寸", "止损", "ATR", "N值", "布林带",
                          "唐奇安", "突破", "海龟", "交易", "策略", "法则",
                          "仓位", "风险", "资金管理", "波动", "系统1", "系统2"]
    has_tech = any(kw in q for kw in technical_keywords)
    is_long_enough = len(q) >= 12

    if has_tech and is_long_enough:
        # 很可能已精确，但让 LLM 最终确认（处理歧义）
        pass

    prompt = EVALUATE_PROMPT.format(question=q)
    response = llm.invoke(prompt)
    answer = _extract_answer(response).strip()
    is_precise = answer.startswith("是")

    return {
        "is_precise": is_precise,
        "search_queries": [q],  # 默认用原问题
    }


def expand_node(state: RAGStateV3) -> dict:
    """扩展节点：将口语化/模糊问题转写为多个专业表述。"""
    llm = _get_llm()
    prompt = EXPAND_PROMPT.format(question=state["question"])
    response = llm.invoke(prompt)
    text = _extract_answer(response).strip()

    # 解析每行一个问题
    expansions = [q.strip() for q in text.split("\n") if q.strip() and len(q.strip()) > 5]
    expansions = expansions[:MAX_EXPANSIONS]  # 最多 3 个

    # 去重 + 保留原问题
    all_queries = [state["question"]]
    for eq in expansions:
        if eq not in all_queries and eq != state["question"]:
            all_queries.append(eq)

    return {"search_queries": all_queries}


def retrieve_node(state: RAGStateV3) -> dict:
    """多查询融合检索节点。

    用所有 search_queries 分别检索，合并结果并按距离排序去重，取 top-K。
    """
    embed_model = _get_embed_model()
    collection = _get_collection()
    queries = state["search_queries"]

    # 收集所有检索结果（带距离和内容）
    seen_texts: set[str] = set()
    all_candidates: list[tuple[float, str, str, int]] = []  # (distance, text, meta_text, page)

    for q in queries:
        q_emb = embed_model.encode(q).tolist()
        results = collection.query(
            query_embeddings=[q_emb],
            n_results=TOP_K_RETRIEVAL,
            include=["documents", "metadatas", "distances"],
        )
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]

        for doc, meta, dist in zip(docs, metas, dists):
            # 去重：相同文本内容只保留距离最小的
            text_key = doc[:100]  # 用前 100 字符做去重 hash
            if text_key not in seen_texts:
                seen_texts.add(text_key)
                all_candidates.append((dist, doc, meta.get("text", doc[:200] + "..."), meta.get("page", "未知")))

    # 按距离升序排序（距离越小越相关）
    all_candidates.sort(key=lambda x: x[0])

    # 取 top-K
    top_k = all_candidates[:TOP_K_RETRIEVAL]

    context = [c[1] for c in top_k]
    sources = [{"page": c[3], "text": c[2], "distance": round(c[0], 4)} for c in top_k]
    distances = [c[0] for c in top_k]
    avg_distance = round(float(np.mean(distances)), 4) if distances else 99.0

    return {
        "context": context,
        "sources": sources,
        "distances": distances,
        "avg_distance": avg_distance,
    }


def generate_node(state: RAGStateV3) -> dict:
    """生成节点：基于融合检索结果生成回答。"""
    llm = _get_llm()

    context_str = "\n\n---\n\n".join(
        f"[页码 {s['page']}] [距离 {s.get('distance', '?')}] {c}"
        for s, c in zip(state["sources"], state["context"])
    )

    history_str = ""
    if state.get("history"):
        for msg in state["history"]:
            role = "用户" if msg["role"] == "user" else "助手"
            history_str += f"{role}: {msg['content']}\n"
    if not history_str:
        history_str = "（无历史对话）"

    prompt = GENERATE_PROMPT.format(
        context=context_str,
        history=history_str,
        question=state["question"],
    )
    response = llm.invoke(prompt)
    return {"answer": _extract_answer(response)}


# ---- 路由 ----

def route_after_evaluate(state: RAGStateV3) -> str:
    """评估节点后的路由：精确 → 直接检索，不精确 → 先扩展。"""
    return "retrieve" if state.get("is_precise", False) else "expand"


# ---- 构建状态图 ----

def build_rag_v3_graph() -> StateGraph:
    """构建 v3 状态图。

    图结构：
        evaluate ──→ [precise] → retrieve → generate → END
                  └→ [vague]  → expand → retrieve → generate → END
    """
    graph = StateGraph(RAGStateV3)

    graph.add_node("evaluate", evaluate_node)
    graph.add_node("expand", expand_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate", generate_node)

    graph.set_entry_point("evaluate")

    graph.add_conditional_edges(
        "evaluate",
        route_after_evaluate,
        {
            "retrieve": "retrieve",
            "expand": "expand",
        },
    )

    graph.add_edge("expand", "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)

    return graph.compile()


rag_v3_app = build_rag_v3_graph()


def ask_question_v3(question: str, history: list[dict] | None = None) -> dict:
    """RAG v3 问答的统一入口。"""
    initial_state: RAGStateV3 = {
        "question": question,
        "is_precise": False,
        "search_queries": [],
        "history": history or [],
        "context": [],
        "sources": [],
        "distances": [],
        "avg_distance": 99.0,
        "answer": "",
    }
    result = rag_v3_app.invoke(initial_state)
    return {
        "answer": result["answer"],
        "sources": result["sources"],
        "avg_distance": result["avg_distance"],
        "is_precise": result["is_precise"],
        "search_queries": result["search_queries"],
        "num_queries": len(result["search_queries"]),
    }


async def ask_question_v3_async(question: str, history: list[dict] | None = None) -> dict:
    """ask_question_v3 的异步包装，在线程池中执行 RAG 流水线。"""
    return await asyncio.to_thread(ask_question_v3, question, history)
