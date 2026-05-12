"""RAG v1 vs v2 vs v3 对比评估脚本。

测试三个版本 RAG 流水线在不同问题类型上的表现，分段输出进度，保存完整回答和来源。

用法：
    source .stock/bin/activate.fish
    env all_proxy=... ANTHROPIC_AUTH_TOKEN=... ... python backend/knowledge/test_rag.py

输出：
    1. 实时：每个问题 × 每个版本的分段进度
    2. 汇总对比表
    3. 完整结果 JSON（含全部 answer + sources）  → test_results.json
    4. 人工评审用 Markdown（方便逐条对比阅读）      → test_results.md
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime

_project_root = Path(__file__).parent.parent.parent  # stock_website/
sys.path.insert(0, str(_project_root))

from backend.services.rag import ask_question as ask_v1
from backend.services.rag_v2 import ask_question_v2 as ask_v2
from backend.services.rag_v3 import ask_question_v3 as ask_v3

# ---- 测试问题集 ----
TEST_QUESTIONS = [
    {
        "id": "Q1",
        "question": "海龟交易法则的入市策略是什么？",
        "type": "精确查询",
        "notes": "预期命中 p238（系统1入市法则）",
    },
    {
        "id": "Q2",
        "question": "海龟如何计算头寸规模？怎么决定买多少？",
        "type": "精确查询",
        "notes": "预期命中 p236-237（头寸规模/N值/ATR）",
    },
    {
        "id": "Q3",
        "question": "止损咋设的？",
        "type": "口语化/模糊查询",
        "notes": "口语化表述，测试改写能力",
    },
    {
        "id": "Q4",
        "question": "海龟交易法则和巴菲特的价值投资有什么区别？",
        "type": "跨章节推理",
        "notes": "书中无直接对比，测试跨领域问题的处理",
    },
    {
        "id": "Q5",
        "question": "什么是N值？怎么用？",
        "type": "精确查询",
        "notes": "预期命中 p230（N值定义）和 p236（N值用法）",
    },
    {
        "id": "Q6",
        "question": "这本书讲比特币吗？",
        "type": "负样本（无关问题）",
        "notes": "预期回答'书中未提及'，不产生幻觉",
    },
]

# ---- 评估函数 ----

def mechanical_score(answer: str, sources: list[dict], question_type: str) -> dict:
    """机械评分：引用、来源数量、回答长度、反幻觉。

    这些是客观可量化的指标，速度快但不够智能。
    """
    source_pages = [s.get("page", 0) for s in sources]
    unique_pages = [p for p in set(source_pages) if isinstance(p, int)]
    has_citation = any(str(p) in answer for p in unique_pages) if unique_pages else False

    return {
        "引用页码列表": unique_pages,
        "回答中带引用": has_citation,
        "来源数量": len(sources),
        "回答字数": len(answer),
        "引用分(0-2)": min(2.0, len(unique_pages) / 2) if has_citation else (0.5 if source_pages else 0),
        "多样性分(0-1)": 1.0 if len(sources) >= 3 else (0.5 if len(sources) >= 1 else 0),
        "详略分(0-1)": 1.0 if len(answer) >= 150 else (0.5 if len(answer) >= 60 else 0.2),
        "反幻觉分(0-1)": 1.0 if "书中未提及" in answer or "没有提及" in answer or "未涉及" in answer else 0.8,
        "总分(0-5)": 0,  # 下面计算
    }


def compute_mechanical_total(scores: dict) -> dict:
    """计算机械评分的总分。"""
    s = scores
    total = s["引用分(0-2)"] + s["多样性分(0-1)"] + s["详略分(0-1)"] + s["反幻觉分(0-1)"]
    s["总分(0-5)"] = round(total, 1)
    return s


# ---- 输出格式化 ----

def hr(title: str = "", char: str = "─", width: int = 80) -> str:
    if title:
        side = (width - len(title) - 2) // 2
        return f"{char * side} {title} {char * side}"
    return char * width


def print_stage_header(stage: int, total: int, version: str, qid: str, question: str) -> None:
    """打印当前测试阶段的头部。"""
    print(f"\n{hr(f' 阶段 {stage}/{total}: {version} — {qid} ')}")
    print(f"  {question}")


def print_version_result(version: str, result: dict, elapsed: float) -> None:
    """格式化打印单个版本的结果摘要。"""
    print(f"\n  [{version}] 耗时 {elapsed:.1f}s")
    if result.get("rewritten_question"):
        print(f"    改写问题: {result['rewritten_question']}")
    if result.get("search_queries"):
        print(f"    查询列表 ({result.get('num_queries', 1)}个): {result['search_queries']}")
    pages = [s.get("page") for s in result.get("sources", [])]
    print(f"    来源页码: {pages}")
    print(f"    平均距离: {result.get('avg_distance', 'N/A')}")
    flags = []
    if result.get("is_precise") is not None:
        flags.append(f"精确={'是' if result['is_precise'] else '否'}")
    if result.get("is_relevant") is not None:
        flags.append(f"相关={'是' if result['is_relevant'] else '否'}")
    if result.get("rewrite_count"):
        flags.append(f"改写次数={result['rewrite_count']}")
    if flags:
        print(f"    状态: {', '.join(flags)}")
    answer_preview = result["answer"][:350].replace("\n", "\n    ")
    print(f"    回答: {answer_preview}{'...' if len(result['answer']) > 350 else ''}")
    s = result.get("score", {})
    print(f"    评分: 引用{s.get('引用分(0-2)','?')} 多样性{s.get('多样性分(0-1)','?')} 详略{s.get('详略分(0-1)','?')} 反幻觉{s.get('反幻觉分(0-1)','?')} = {s.get('总分(0-5)','?')}")


# ---- 主测试流程 ----

def run_tests() -> None:
    versions = {
        "v1": ask_v1,
        "v2": ask_v2,
        "v3": ask_v3,
    }

    total_stages = len(TEST_QUESTIONS) * len(versions)
    stage = 0
    all_results = []
    summary_rows = []

    print(hr("RAG v1 vs v2 vs v3 对比评估"))
    print(f"  测试问题: {len(TEST_QUESTIONS)} 个")
    print(f"  测试版本: {len(versions)} 个 (v1, v2, v3)")
    print(f"  总测试数: {total_stages} 次")
    print(f"  开始时间: {datetime.now().strftime('%H:%M:%S')}")

    for item in TEST_QUESTIONS:
        qid = item["id"]
        qtext = item["question"]
        qtype = item["type"]

        result_row = {
            "id": qid,
            "question": qtext,
            "type": qtype,
            "notes": item.get("notes", ""),
            "versions": {},
        }

        for ver_name, ver_func in versions.items():
            stage += 1
            print_stage_header(stage, total_stages, ver_name, qid, qtext)

            t0 = time.time()
            try:
                raw = ver_func(qtext)
                elapsed = time.time() - t0

                # 提取该版本的特定字段
                ver_result = {
                    "answer": raw["answer"],
                    "sources": raw["sources"],
                    "elapsed": round(elapsed, 1),
                }

                # 版本特有字段
                for key in ["avg_distance", "is_relevant", "rewrite_count",
                            "rewritten_question", "is_precise", "search_queries",
                            "num_queries", "distances"]:
                    if key in raw:
                        ver_result[key] = raw[key]

                # 计算评分
                score = mechanical_score(raw["answer"], raw["sources"], qtype)
                score = compute_mechanical_total(score)
                ver_result["score"] = score

                print_version_result(ver_name, ver_result, elapsed)

            except Exception as e:
                elapsed = time.time() - t0
                ver_result = {
                    "answer": "",
                    "sources": [],
                    "elapsed": round(elapsed, 1),
                    "error": str(e),
                    "score": {"总分(0-5)": 0},
                }
                print(f"\n  [{ver_name}] ❌ 错误 ({elapsed:.1f}s): {e}")

            result_row["versions"][ver_name] = ver_result
            summary_rows.append({
                "qid": qid,
                "ver": ver_name,
                "type": qtype,
                "score": ver_result.get("score", {}).get("总分(0-5)", 0),
                "elapsed": ver_result.get("elapsed", 0),
                "sources": [s.get("page") for s in ver_result.get("sources", [])],
                "answer_len": len(ver_result.get("answer", "")),
            })

            time.sleep(0.5)  # API 限流保护

        all_results.append(result_row)

    # ---- 汇总报告 ----
    print(f"\n\n{hr(' 汇总对比报告 ')}")

    # 表头
    header = f"{'ID':<4} {'类型':<10} {'v1分':<6} {'v2分':<6} {'v3分':<6} {'v1耗时':<8} {'v2耗时':<8} {'v3耗时':<8}"
    print(header)
    print("-" * len(header))

    for item in all_results:
        vers = item["versions"]
        v1s = vers.get("v1", {}).get("score", {}).get("总分(0-5)", 0)
        v2s = vers.get("v2", {}).get("score", {}).get("总分(0-5)", 0)
        v3s = vers.get("v3", {}).get("score", {}).get("总分(0-5)", 0)
        v1t = f"{vers.get('v1', {}).get('elapsed', 0)}s"
        v2t = f"{vers.get('v2', {}).get('elapsed', 0)}s"
        v3t = f"{vers.get('v3', {}).get('elapsed', 0)}s"
        print(f"{item['id']:<4} {item['type']:<10} {v1s:<6.1f} {v2s:<6.1f} {v3s:<6.1f} {v1t:<8} {v2t:<8} {v3t:<8}")

    # 平均分
    print("-" * len(header))
    for ver_name in ["v1", "v2", "v3"]:
        scores = [r["versions"].get(ver_name, {}).get("score", {}).get("总分(0-5)", 0)
                  for r in all_results]
        times = [r["versions"].get(ver_name, {}).get("elapsed", 0) for r in all_results]
        avg_s = sum(scores) / len(scores) if scores else 0
        avg_t = sum(times) / len(times) if times else 0
        print(f"  {ver_name} 平均分: {avg_s:.1f}/5.0  平均耗时: {avg_t:.1f}s")

    print(f"\n  完成时间: {datetime.now().strftime('%H:%M:%S')}")
    print(f"  注意：机械评分仅评估引用/字数/长度等量化指标，不代表回答准确性。")
    print(f"  建议阅读下方 JSON/Markdown 文件中的完整回答做最终判断。")

    # ---- 保存完整结果 ----
    output_dir = Path(__file__).parent

    # JSON: 完整数据
    json_path = output_dir / "test_results.json"
    export_data = {
        "test_time": datetime.now().isoformat(),
        "questions": TEST_QUESTIONS,
        "results": all_results,
        "summary": summary_rows,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)
    print(f"\n  完整 JSON 已保存: {json_path}")

    # Markdown: 方便逐条对比阅读
    md_path = output_dir / "test_results.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# RAG v1 vs v2 vs v3 对比测试结果\n\n")
        f.write(f"> 测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n")
        f.write(f"> 测试问题: {len(TEST_QUESTIONS)} 个 × 3 版本 = {total_stages} 次  \n\n")
        f.write(f"---\n\n")

        for item in all_results:
            f.write(f"## {item['id']}: {item['question']}\n\n")
            f.write(f"**类型**: {item['type']}  \n")
            f.write(f"**说明**: {item.get('notes', '')}  \n\n")

            for ver_name in ["v1", "v2", "v3"]:
                ver = item["versions"].get(ver_name, {})
                f.write(f"### {ver_name}\n\n")
                f.write(f"- 耗时: {ver.get('elapsed', '?')}s\n")
                if ver.get("rewritten_question"):
                    f.write(f"- 改写问题: {ver['rewritten_question']}\n")
                if ver.get("search_queries"):
                    f.write(f"- 查询列表: {ver['search_queries']}\n")
                if ver.get("is_precise") is not None:
                    f.write(f"- 精确评估: {'是（跳过扩展）' if ver['is_precise'] else '否（触发扩展）'}\n")
                if ver.get("is_relevant") is not None:
                    f.write(f"- 相关性: {'是' if ver['is_relevant'] else '否'}\n")
                f.write(f"- 平均距离: {ver.get('avg_distance', 'N/A')}\n")
                pages = [s.get("page") for s in ver.get("sources", [])]
                f.write(f"- 来源页码: {pages}\n")
                score = ver.get("score", {})
                f.write(f"- 机械评分: 引用{score.get('引用分(0-2)','?')} + 多样性{score.get('多样性分(0-1)','?')} + 详略{score.get('详略分(0-1)','?')} + 反幻觉{score.get('反幻觉分(0-1)','?')} = **{score.get('总分(0-5)','?')}**\n\n")
                f.write(f"**回答**:\n\n{ver.get('answer', '(无)')}\n\n")

                if ver.get("sources"):
                    f.write(f"**检索来源**:\n\n")
                    for s in ver["sources"]:
                        f.write(f"- p{s.get('page', '?')} (距离={s.get('distance', '?')}): {s.get('text', '')}\n")
                    f.write("\n")
                else:
                    f.write(f"**检索来源**: 无\n\n")
                f.write("---\n\n")

        # 汇总表
        f.write(f"## 汇总对比\n\n")
        f.write(f"| ID | 类型 | v1 分 | v2 分 | v3 分 | v1 耗时 | v2 耗时 | v3 耗时 |\n")
        f.write(f"|----|------|-------|-------|-------|---------|---------|--------|\n")
        for item in all_results:
            vers = item["versions"]
            v1s = vers.get("v1", {}).get("score", {}).get("总分(0-5)", 0)
            v2s = vers.get("v2", {}).get("score", {}).get("总分(0-5)", 0)
            v3s = vers.get("v3", {}).get("score", {}).get("总分(0-5)", 0)
            v1t = f"{vers.get('v1', {}).get('elapsed', 0)}s"
            v2t = f"{vers.get('v2', {}).get('elapsed', 0)}s"
            v3t = f"{vers.get('v3', {}).get('elapsed', 0)}s"
            f.write(f"| {item['id']} | {item['type']} | {v1s:.1f} | {v2s:.1f} | {v3s:.1f} | {v1t} | {v2t} | {v3t} |\n")

        f.write(f"\n> 机械评分仅评估引用/字数等量化指标，不代表准确性。请逐条阅读各版本回答做主观判断。\n")

    print(f"  评审用 Markdown 已保存: {md_path}")


if __name__ == "__main__":
    run_tests()
