"""AI 新闻摘要服务 — 根据新闻标题列表调用 LLM 生成当日新闻总结。"""

import asyncio
from langchain_anthropic import ChatAnthropic
from ..config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, ANTHROPIC_BASE_URL

_llm: ChatAnthropic | None = None


def _get_llm() -> ChatAnthropic:
    """延迟初始化 ChatAnthropic 单例（复用 RAG 配置）。"""
    global _llm
    if _llm is None:
        kwargs = dict(
            model=ANTHROPIC_MODEL,
            api_key=ANTHROPIC_API_KEY,
            temperature=0.5,
            max_tokens=1024,
        )
        if ANTHROPIC_BASE_URL:
            kwargs["base_url"] = ANTHROPIC_BASE_URL
        _llm = ChatAnthropic(**kwargs)
    return _llm


def _extract_answer(response) -> str:
    """兼容标准 Anthropic 和 DeepSeek 两种响应格式。"""
    content = response.content
    if isinstance(content, list):
        return "".join(
            block.get("text", "") for block in content if isinstance(block, dict)
        )
    return str(content)


def generate_summary(headlines: list[dict]) -> str:
    """根据新闻标题列表生成当日新闻摘要。

    Args:
        headlines: [{title, link}, ...] 每条新闻的标题和链接

    Returns:
        中文摘要文本，按主题分点列出
    """
    # 构建标题列表（含分类标签）
    lines: list[str] = []
    for h in headlines:
        title = h.get("title", "")
        link = h.get("link", "")
        # 从链接中提取分类
        parts = link.split("/")
        category = parts[3] if len(parts) > 3 else ""
        tag = f"[{category}] " if category else ""
        lines.append(f"{tag}{title}")

    titles_text = "\n".join(lines)

    prompt = f"""你是专业的新闻编辑。以下是 The Guardian 今日新闻标题列表。

请根据这些标题总结今日发生的主要新闻主题，每个主题用几句话进行概括，可以包含主要事件和具体细节。

请用中文回复，使用以下格式：

【主题标题】主要内容

今日新闻标题列表：
{titles_text}"""

    llm = _get_llm()
    response = llm.invoke(prompt)
    return _extract_answer(response)


async def generate_summary_async(headlines: list[dict]) -> str:
    """generate_summary 的异步包装，在线程池中执行 LLM 调用。"""
    return await asyncio.to_thread(generate_summary, headlines)
