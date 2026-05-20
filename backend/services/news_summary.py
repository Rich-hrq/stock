"""AI 新闻摘要服务 — 根据新闻标题列表调用 LLM 生成当日新闻总结。"""

import asyncio
from langchain_anthropic import ChatAnthropic
from ..config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, ANTHROPIC_BASE_URL

_llm: ChatAnthropic | None = None
_summary_semaphore = asyncio.Semaphore(2)

SUMMARY_HARD_TIMEOUT = 50  # asyncio.wait_for 硬超时（秒）
MAX_HEADLINES = 25         # 只取前 N 条标题，控制 prompt 长度


class SummaryError(Exception):
    """摘要生成异常，携带可展示给用户的错误原因分类。"""

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        self.detail = detail
        super().__init__(detail or reason)


def _get_llm() -> ChatAnthropic:
    """延迟初始化 ChatAnthropic 单例 — 每次重建确保使用最新配置。"""
    global _llm
    kwargs = dict(
        model=ANTHROPIC_MODEL,
        api_key=ANTHROPIC_API_KEY,
        temperature=0.5,
        max_tokens=2048,               # 2048 足够新闻摘要，降低生成耗时
        default_request_timeout=40,    # 单次 HTTP 请求 40s 超时
        max_retries=0,                 # 不重试，由 asyncio.wait_for 统一控制
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

    仅取前 MAX_HEADLINES 条标题以控制 prompt 长度和 LLM 推理耗时。

    Raises:
        SummaryError: 带分类标签的错误
    """
    truncated = headlines[:MAX_HEADLINES]
    skipped = len(headlines) - len(truncated)

    lines: list[str] = []
    for h in truncated:
        title = h.get("title", "")
        link = h.get("link", "")
        parts = link.split("/")
        category = parts[3] if len(parts) > 3 else ""
        tag = f"[{category}] " if category else ""
        lines.append(f"{tag}{title}")

    titles_text = "\n".join(lines)

    skip_hint = f"\n（注：共 {len(headlines)} 条新闻，已取前 {MAX_HEADLINES} 条）" if skipped else ""

    prompt = f"""你是专业的新闻编辑。以下是 The Guardian 今日新闻标题列表（共 {len(truncated)} 条）。

请根据这些标题总结今日发生的主要新闻主题，用简洁的语言概括每个主题的核心内容。

请用中文回复，使用以下格式：

【主题标题】主要内容

今日新闻标题列表：
{titles_text}{skip_hint}"""

    llm = _get_llm()

    try:
        response = llm.invoke(prompt)
    except Exception as e:
        _classify_and_raise(e)

    return _extract_answer(response)


def _classify_and_raise(exc: Exception) -> None:
    """根据异常类型分类并抛出 SummaryError。"""
    msg = str(exc)

    if any(kw in msg.lower() for kw in (
        "authentication", "unauthorized", "invalid api key",
        "could not resolve authentication", "incorrect api key",
        "401", "403",
    )):
        raise SummaryError("apikey", f"API Key 无效或过期 — {msg}")

    if any(kw in msg.lower() for kw in ("rate limit", "429", "too many requests")):
        raise SummaryError("ratelimit", f"API 请求被限流 — {msg}")

    if any(kw in msg.lower() for kw in ("timeout", "timed out", "connect error")):
        raise SummaryError("timeout", f"LLM 请求超时（{SUMMARY_HARD_TIMEOUT}s 硬限制）— {msg}")

    if any(kw in msg.lower() for kw in ("model not found", "invalid model", "404")):
        raise SummaryError("model", f"模型 {ANTHROPIC_MODEL} 不存在或不可用 — {msg}")

    if any(kw in msg.lower() for kw in (
        "connection", "dns", "resolve", "refused", "network",
    )):
        raise SummaryError("network", f"网络连接失败 — {msg}")

    raise SummaryError("unknown", f"未知错误 — {msg}")


async def generate_summary_async(headlines: list[dict]) -> str:
    """异步包装：信号量限流 + 线程池执行 + 硬超时兜底。"""
    async with _summary_semaphore:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(generate_summary, headlines),
                timeout=SUMMARY_HARD_TIMEOUT,
            )
        except asyncio.TimeoutError:
            raise SummaryError(
                "timeout",
                f"摘要生成超过 {SUMMARY_HARD_TIMEOUT}s 硬限制，已取消。"
                "可能原因：LLM API 响应过慢或并发过高",
            )
