"""升级版 RAG 问答服务 (v2)：问题改写 + 相关性判断 + 条件路由。

相比 v1（简单 retrieve → generate），v2 新增：
    1. 问题改写节点：将用户模糊问题优化为检索友好的表述
    2. 相关性判断节点：基于向量距离判断检索结果是否真正相关
    3. 条件路由：
       - 高度相关 → 直接生成自信回答
       - 低相关 → 二次改写 → 重新检索 → 生成(带不确定性声明)

流水线流程：
    START → rewrite → retrieve → judge
                                  ├─ relevant ──→ generate → END
                                  └─ not_relevant + 未达上限 → rewrite_v2 → retrieve → judge (回环)
                                  └─ not_relevant + 已达上限 → generate_uncertain → END
"""

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

# 相关性阈值：基于 L2 距离（ChromaDB 默认使用欧几里得距离）
# 本嵌入模型 (multilingual-MiniLM-L12-v2, 384维) 的实际距离范围：
#   高度相关: < 8.0     (检索到的内容与问题语义相关)
#   低相关:   8.0 - 12.0  (有一定关联但不精确)
#   基本无关: > 12.0     (随机噪声级别)
# 这些阈值基于 6 个测试问题的实测数据校准
RELEVANCE_THRESHOLD = 10.0
MAX_REWRITE_COUNT = 1  # 最多额外改写 1 次


# ---- 状态定义 ----
class RAGStateV2(TypedDict):
    question: str              # 原始问题
    rewritten_question: str    # 改写后用于检索的问题
    history: list[dict]        # 对话历史
    context: list[str]         # 检索到的文本块
    sources: list[dict]        # 来源 [{page, text}]
    distances: list[float]     # 检索结果的向量距离
    avg_distance: float        # 平均距离
    is_relevant: bool          # 相关性判断结果
    rewrite_count: int         # 改写次数（防无限循环）
    answer: str


# ---- 全局单例（与 v1 共用 ChromaDB 和嵌入模型） ----
_embed_model_v2: SentenceTransformer | None = None
_chroma_collection_v2: chromadb.Collection | None = None
_llm_v2: ChatAnthropic | None = None


def _get_embed_model() -> SentenceTransformer:
    global _embed_model_v2
    if _embed_model_v2 is None:
        _embed_model_v2 = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    return _embed_model_v2


def _get_collection() -> chromadb.Collection:
    global _chroma_collection_v2
    if _chroma_collection_v2 is None:
        client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
        _chroma_collection_v2 = client.get_collection("turtle_trading")
    return _chroma_collection_v2


def _get_llm() -> ChatAnthropic:
    global _llm_v2
    if _llm_v2 is None:
        kwargs = dict(
            model=ANTHROPIC_MODEL,
            api_key=ANTHROPIC_API_KEY,
            temperature=0.3,
            max_tokens=2048,
        )
        if ANTHROPIC_BASE_URL:
            kwargs["base_url"] = ANTHROPIC_BASE_URL
        _llm_v2 = ChatAnthropic(**kwargs)
    return _llm_v2


def _extract_answer(response) -> str:
    """兼容 Anthropic 标准 API 和 DeepSeek 兼容 API 的响应格式。"""
    content = response.content
    if isinstance(content, list):
        return "".join(block.get("text", "") for block in content if isinstance(block, dict))
    return str(content)


# ---- LangGraph 节点 ----

# 问题改写 Prompt（将口语化/模糊问题优化为检索友好的精确表述）
REWRITE_PROMPT = """你是一个搜索查询优化专家。请将用户关于《海龟交易法则》的问题改写为更适合在书中原文检索的表述。

规则：
1. 提取问题中的核心概念和关键词
2. 补充可能的同义词和相关术语（例如"入场"可扩展为"入市 突破 做多 做空"）
3. 去除寒暄和无关内容
4. 只输出改写后的问题，不要任何解释

原始问题：{question}

改写后的问题："""


def rewrite_node(state: RAGStateV2) -> dict:
    """问题改写节点：将用户问题优化为更适合检索的表述。"""
    llm = _get_llm()
    prompt = REWRITE_PROMPT.format(question=state["question"])
    response = llm.invoke(prompt)
    rewritten = _extract_answer(response).strip()
    return {
        "rewritten_question": rewritten,
        "rewrite_count": state.get("rewrite_count", 0) + 1,
    }


def retrieve_node(state: RAGStateV2) -> dict:
    """检索节点：使用改写后的问题（如存在）检索 ChromaDB。"""
    embed_model = _get_embed_model()
    collection = _get_collection()

    query_text = state.get("rewritten_question") or state["question"]
    query_embedding = embed_model.encode(query_text).tolist()

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=TOP_K_RETRIEVAL,
        include=["documents", "metadatas", "distances"],
    )

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    context = []
    sources = []
    for doc, meta, dist in zip(docs, metas, distances):
        context.append(doc)
        sources.append({
            "page": meta.get("page", "未知"),
            "text": doc[:200] + "...",
            "distance": round(dist, 4),
        })

    avg_distance = float(np.mean(distances)) if distances else 99.0

    return {
        "context": context,
        "sources": sources,
        "distances": list(distances),
        "avg_distance": round(avg_distance, 4),
    }


def judge_node(state: RAGStateV2) -> dict:
    """相关性判断节点：基于向量距离判断检索结果是否真正相关。

    逻辑：
    - 平均距离 < RELEVANCE_THRESHOLD → 检索结果语义相关
    - 平均距离 >= RELEVANCE_THRESHOLD → 检索结果可能无关
    """
    avg_dist = state.get("avg_distance", 99.0)
    is_relevant = avg_dist < RELEVANCE_THRESHOLD
    return {"is_relevant": is_relevant}


# 标准生成 Prompt（高相关性时使用）
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

# 不确定性生成 Prompt（低相关性时使用）
GENERATE_UNCERTAIN_PROMPT = """你是海龟交易法则的专家助手。用户提出了一个问题，但在书中没有找到高度匹配的原文内容。

以下是从书中检索到的"可能相关"的内容（注意：这些内容可能与用户问题关联度不高）：
---
{context}
---

历史对话：
{history}

用户问题：{question}

请按照以下规则回答：
1. 首先明确告知用户"根据现有检索结果，书中相关原文匹配度较低，以下回答可能存在不确定性"
2. 如果检索内容有部分相关，尽量提取有用信息回答
3. 如果确实完全不相关，请告知用户并建议换一种方式提问
4. 不要编造信息
5. 使用中文回答
"""


def generate_node(state: RAGStateV2) -> dict:
    """生成节点（高相关性）：基于可靠上下文生成自信回答。"""
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


def generate_uncertain_node(state: RAGStateV2) -> dict:
    """生成节点（低相关性）：基于不确定上下文生成回答，附带免责声明。"""
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

    prompt = GENERATE_UNCERTAIN_PROMPT.format(
        context=context_str,
        history=history_str,
        question=state["question"],
    )

    response = llm.invoke(prompt)
    return {"answer": _extract_answer(response)}


# ---- 条件路由 ----

def route_after_judge(state: RAGStateV2) -> str:
    """判断后的路由逻辑。

    Returns:
        "generate": 检索结果高度相关，直接生成自信回答
        "rewrite_v2": 检索结果低相关且还有改写机会，改写后重试
        "generate_uncertain": 检索结果低相关且已达改写上限，生成带免责的回答
    """
    if state.get("is_relevant", False):
        return "generate"

    rewrite_count = state.get("rewrite_count", 0)
    if rewrite_count < MAX_REWRITE_COUNT + 1:  # +1 因为初始 rewrite 已经算一次
        return "rewrite_v2"
    else:
        return "generate_uncertain"


# ---- 构建状态图 ----

def build_rag_v2_graph() -> StateGraph:
    """构建升级版 LangGraph RAG 流水线。

    图结构：
        rewrite → retrieve → judge
        ├─ judge → [relevant] → generate → END
        └─ judge → [not_relevant]
                        ├─ [可改写] → rewrite_v2 → retrieve → judge (回环)
                        └─ [不可改写] → generate_uncertain → END
    """
    graph = StateGraph(RAGStateV2)

    # 添加节点
    graph.add_node("rewrite", rewrite_node)
    graph.add_node("rewrite_v2", rewrite_node)  # 二次改写，逻辑相同
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("judge", judge_node)
    graph.add_node("generate", generate_node)
    graph.add_node("generate_uncertain", generate_uncertain_node)

    # 入口 → 改写
    graph.set_entry_point("rewrite")

    # 改写 → 检索 → 判断
    graph.add_edge("rewrite", "retrieve")
    graph.add_edge("rewrite_v2", "retrieve")
    graph.add_edge("retrieve", "judge")

    # 条件路由：判断后分三路
    graph.add_conditional_edges(
        "judge",
        route_after_judge,
        {
            "generate": "generate",
            "rewrite_v2": "rewrite_v2",
            "generate_uncertain": "generate_uncertain",
        },
    )

    # 生成节点 → 结束
    graph.add_edge("generate", END)
    graph.add_edge("generate_uncertain", END)

    return graph.compile()


# 模块级编译实例
rag_v2_app = build_rag_v2_graph()


def ask_question_v2(question: str, history: list[dict] | None = None) -> dict:
    """RAG v2 问答的统一入口。

    Args:
        question: 用户的问题
        history: 历史对话记录 [{role, content}, ...]

    Returns:
        {
            "answer": str,
            "sources": [{"page": int, "text": str, "distance": float}],
            "avg_distance": float,
            "is_relevant": bool,
            "rewrite_count": int,
            "rewritten_question": str,
        }
    """
    initial_state: RAGStateV2 = {
        "question": question,
        "rewritten_question": "",
        "history": history or [],
        "context": [],
        "sources": [],
        "distances": [],
        "avg_distance": 99.0,
        "is_relevant": False,
        "rewrite_count": 0,
        "answer": "",
    }
    result = rag_v2_app.invoke(initial_state)
    return {
        "answer": result["answer"],
        "sources": result["sources"],
        "avg_distance": result["avg_distance"],
        "is_relevant": result["is_relevant"],
        "rewrite_count": result["rewrite_count"],
        "rewritten_question": result.get("rewritten_question", ""),
    }
