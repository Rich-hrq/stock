# Feature: 多 LLM 兼容（DeepSeek API 集成）

## 需求背景

项目最初使用 Claude（Anthropic 官方 API），但为了降低成本和提高可访问性，需要支持 DeepSeek 等兼容 Anthropic API 格式的模型。

## 需求总结

| 项目 | 决策 |
|------|------|
| LLM 框架 | langchain-anthropic（ChatAnthropic） |
| 兼容方式 | 通过 ANTHROPIC_BASE_URL 指向兼容 API |
| 支持的模型 | Claude Opus/Sonnet/Haiku、DeepSeek V3/V4 |
| 配置方式 | 环境变量 `ANTHROPIC_BASE_URL` + `ANTHROPIC_MODEL` |

---

## 功能边界

### 做什么
- 通过环境变量切换 LLM 后端
- 兼容 DeepSeek 的 Anthropic API 格式
- 处理 DeepSeek 返回的 content blocks 列表格式差异

### 不做什么
- 不支持 OpenAI API 格式（仅 Anthropic 兼容）
- 不支持同时使用多个 LLM
- 不提供前端模型切换

---

## 核心设计

```python
# config.py
ANTHROPIC_AUTH_TOKEN = os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL")  # DeepSeek: https://api.deepseek.com/anthropic
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# 使用时
from langchain_anthropic import ChatAnthropic
llm = ChatAnthropic(
    model=ANTHROPIC_MODEL,
    api_key=ANTHROPIC_AUTH_TOKEN,
    base_url=ANTHROPIC_BASE_URL,
)
```

### DeepSeek 内容格式兼容

DeepSeek 返回 `content: [{type: "text", text: "..."}]` 列表格式，需在响应处理时优先检查列表格式再 fallback 到字符串格式。

---

## 边界条件

- 不设置环境变量则使用默认 Claude API
- DeepSeek API 不可用时的降级策略由用户决定
- 不同模型对 system prompt 处理方式可能不同

---

## 文件变更清单

| 文件 | 操作 |
|------|------|
| `backend/config.py` | 修改（新增 LLM 环境变量） |
| `backend/services/rag_v3.py` | 修改（兼容 DeepSeek 内容格式） |
| `backend/services/news_summary.py` | 复用配置 |

---

## 风险与注意事项

- DeepSeek 的 Anthropic 兼容 API 可能不完全兼容最新版本
- 不同模型的 token 限制和计费方式不同
- 切换到小模型时可能影响 RAG 回答质量
