"""RAG v1 vs v2 对比评估脚本。

测试两组 RAG 流水线在不同问题类型上的表现差异，输出对比报告。

用法：
    source .stock/bin/activate.fish
    # 需设置 ANTHROPIC_AUTH_TOKEN / ANTHROPIC_BASE_URL 环境变量
    python backend/knowledge/test_rag.py

输出：
    1. 每个问题的详细对比（v1 vs v2 的回答、来源、距离）
    2. 汇总评分表
"""

import sys
import json
import time
from pathlib import Path

# 将 stock_website/ 加入 sys.path，使 backend 成为可导入的包
_project_root = Path(__file__).parent.parent.parent  # stock_website/
sys.path.insert(0, str(_project_root))

from backend.services.rag import ask_question as ask_v1
from backend.services.rag_v2 import ask_question_v2 as ask_v2


# ---- 测试问题集 ----
# 覆盖不同类型：精确查询、模糊查询、跨章节推理、书中无相关内容

TEST_QUESTIONS = [
    {
        "id": "Q1",
        "question": "海龟交易法则的入市策略是什么？",
        "type": "精确查询",
        "expected_pages": [238],  # 系统1入市法则
    },
    {
        "id": "Q2",
        "question": "海龟如何计算头寸规模？怎么决定买多少？",
        "type": "精确查询",
        "expected_pages": [236, 237],  # 头寸规模/N值
    },
    {
        "id": "Q3",
        "question": "止损咋设的？",
        "type": "口语化/模糊查询",
        "expected_pages": [237, 238],  # 止损策略
    },
    {
        "id": "Q4",
        "question": "海龟交易法则和巴菲特的价值投资有什么区别？",
        "type": "跨章节推理/书中无直接答案",
        "expected_pages": [],  # 书中可能不会直接对比
    },
    {
        "id": "Q5",
        "question": "什么是N值？怎么用？",
        "type": "精确查询",
        "expected_pages": [234, 236],  # N值/ATR定义
    },
    {
        "id": "Q6",
        "question": "这本书讲比特币吗？",
        "type": "书中无相关内容（负样本）",
        "expected_pages": [],
    },
]


def evaluate_answer(answer: str, sources: list[dict], question_type: str) -> dict:
    """对单个回答进行自动评分。

    评分维度：
    - 引用页码数 (0-2分): 回答是否引用了具体页码
    - 来源数量 (0-1分): 是否有至少 2 个不同来源
    - 回答长度 (0-1分): 是否足够详细 (>100字 = 1分)
    - 拒绝幻觉 (0-1分): 对于书中无相关内容，是否正确说"书中未提及"
    """
    source_pages = [s.get("page", 0) for s in sources]
    unique_pages = len(set(source_pages))
    has_citation = any(str(p) in answer for p in source_pages) if source_pages else False

    score_citation = min(2.0, unique_pages / 2) if has_citation else (0.5 if source_pages else 0)
    score_sources = 1.0 if len(sources) >= 2 else (0.5 if len(sources) >= 1 else 0)
    score_length = 1.0 if len(answer) >= 100 else (0.5 if len(answer) >= 50 else 0.2)
    score_no_hallucination = 1.0  # 默认满分，需要人工或 LLM 判断
    if "书中未提及" in answer or "没有找到" in answer or "未找到" in answer:
        score_no_hallucination = 1.0

    total = score_citation + score_sources + score_length + score_no_hallucination

    return {
        "引用页码数": unique_pages,
        "是否有引用": has_citation,
        "来源数量": len(sources),
        "回答长度": len(answer),
        "引用分(0-2)": round(score_citation, 1),
        "来源分(0-1)": round(score_sources, 1),
        "长度分(0-1)": round(score_length, 1),
        "反幻觉分(0-1)": round(score_no_hallucination, 1),
        "总分(0-5)": round(total, 1),
    }


def run_test() -> None:
    """主测试流程。"""
    print("=" * 80)
    print("RAG v1 vs v2 对比评估")
    print(f"测试问题数: {len(TEST_QUESTIONS)}")
    print("=" * 80)

    results = []

    for item in TEST_QUESTIONS:
        qid = item["id"]
        qtext = item["question"]
        qtype = item["type"]

        print(f"\n{'=' * 80}")
        print(f"{qid} [{qtype}] {qtext}")
        print(f"{'=' * 80}")

        # ---- v1 ----
        print("\n--- v1 (简单 retrieve → generate) ---")
        t0 = time.time()
        try:
            r1 = ask_v1(qtext)
            t1 = time.time() - t0
            e1 = evaluate_answer(r1["answer"], r1["sources"], qtype)
            print(f"  耗时: {t1:.1f}s")
            print(f"  来源页: {[s['page'] for s in r1['sources']]}")
            print(f"  评分: {json.dumps(e1, ensure_ascii=False)}")
            print(f"  回答摘要: {r1['answer'][:200]}...")
        except Exception as e:
            r1 = None
            t1 = time.time() - t0
            e1 = None
            print(f"  错误: {e}")

        time.sleep(0.5)  # 避免 API 限流

        # ---- v2 ----
        print("\n--- v2 (rewrite → retrieve → judge → 条件路由) ---")
        t0 = time.time()
        try:
            r2 = ask_v2(qtext)
            t2 = time.time() - t0
            e2 = evaluate_answer(r2["answer"], r2["sources"], qtype)
            print(f"  耗时: {t2:.1f}s")
            print(f"  改写后问题: {r2.get('rewritten_question', 'N/A')}")
            print(f"  平均距离: {r2.get('avg_distance', 'N/A')}")
            print(f"  相关性: {r2.get('is_relevant', 'N/A')}")
            print(f"  改写次数: {r2.get('rewrite_count', 'N/A')}")
            print(f"  来源页: {[s['page'] for s in r2['sources']]}")
            print(f"  评分: {json.dumps(e2, ensure_ascii=False)}")
            print(f"  回答摘要: {r2['answer'][:200]}...")
        except Exception as e:
            r2 = None
            t2 = time.time() - t0
            e2 = None
            print(f"  错误: {e}")

        results.append({
            "id": qid,
            "question": qtext,
            "type": qtype,
            "v1": {"time": round(t1, 1) if r1 else None, "score": e1, "sources": r1["sources"] if r1 else []},
            "v2": {
                "time": round(t2, 1) if r2 else None,
                "score": e2,
                "sources": r2["sources"] if r2 else [],
                "is_relevant": r2.get("is_relevant") if r2 else None,
                "avg_distance": r2.get("avg_distance") if r2 else None,
                "rewrite_count": r2.get("rewrite_count") if r2 else None,
                "rewritten": r2.get("rewritten_question", "") if r2 else "",
            },
        })

        time.sleep(0.5)

    # ---- 汇总报告 ----
    print("\n\n" + "=" * 80)
    print("汇总对比报告")
    print("=" * 80)

    print(f"\n{'ID':<4} {'类型':<12} {'v1 总分':<10} {'v2 总分':<10} {'v2 相关':<8} {'v2 距离':<8} {'v2 改写次数':<10}")
    print("-" * 80)

    v1_scores = []
    v2_scores = []

    for r in results:
        v1s = r["v1"]["score"]["总分(0-5)"] if r["v1"]["score"] else 0
        v2s = r["v2"]["score"]["总分(0-5)"] if r["v2"]["score"] else 0
        v1_scores.append(v1s)
        v2_scores.append(v2s)

        rel = "是" if r["v2"].get("is_relevant") else "否"
        dist = f"{r['v2'].get('avg_distance', 'N/A')}"
        rc = r["v2"].get("rewrite_count", "N/A")

        print(f"{r['id']:<4} {r['type']:<12} {v1s:<10.1f} {v2s:<10.1f} {rel:<8} {dist:<8} {rc:<10}")

    avg_v1 = sum(v1_scores) / len(v1_scores) if v1_scores else 0
    avg_v2 = sum(v2_scores) / len(v2_scores) if v2_scores else 0

    print("-" * 80)
    print(f"\n{'v1 平均分':<20} {avg_v1:.1f}/5.0")
    print(f"{'v2 平均分':<20} {avg_v2:.1f}/5.0")
    print(f"\n注意：自动评分基于引用/来源/长度等机械指标，不代表回答质量的全部维度。")
    print("建议结合人工阅读各回答做最终判断。")

    # 保存详细结果到 JSON
    output_path = Path(__file__).parent / "test_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n详细结果已保存至: {output_path}")


if __name__ == "__main__":
    run_test()
