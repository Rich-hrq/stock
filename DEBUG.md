# DEBUG 记录

记录运行过程中的报错、原因与修复经验，避免重复踩坑。

---

## 运行测试时的注意事项

- 首次启动前需设置 `ANTHROPIC_API_KEY` 环境变量（RAG 对话功能依赖）
- 首次启动前需运行 `python backend/knowledge/ingest.py` 构建向量知识库
- 美股数据获取需设置代理：`set -x all_proxy http://127.0.0.1:7897`（fish shell）

---

## 首次启动出现端口占用

**现象**：uvicorn 启动后 curl 返回 `Connection refused`

**原因**：多次后台启动 uvicorn 导致端口 8000 残留

**解决**：`lsof -ti:8000 | xargs kill -9` 清理端口后重启

---

## 聊天 API 需要 ANTHROPIC_API_KEY

**现象**：`POST /api/chat` 返回 500:"Could not resolve authentication method"

**原因**：Anthropic SDK 未检测到有效的 API Key

**解决**：启动前设置环境变量。支持 `ANTHROPIC_API_KEY` 或 `ANTHROPIC_AUTH_TOKEN`：
```fish
set -x ANTHROPIC_AUTH_TOKEN sk-ant-xxx   # fish
```
或
```bash
export ANTHROPIC_AUTH_TOKEN=sk-ant-xxx   # bash
```

---

## 端口 8000 被占用导致启动失败

**现象**：执行 `uvicorn` 后报 `[Errno 48] address already in use`

**原因**：上一次退出时进程未完全清理，端口仍被占用

**解决**：
```bash
lsof -ti:8000 | xargs kill -9
sleep 2
# 重新启动
```

---

## HuggingFace 嵌入模型下载超时

**现象**：`ingest.py` 运行时报 `timed out` 或 `Connection reset by peer`，无法下载 `paraphrase-multilingual-MiniLM-L12-v2`

**原因**：HuggingFace CDN 在国内无法直连，与 Yahoo Finance 同原因

**解决**：设置代理后运行：
```fish
all_proxy=http://127.0.0.1:7897 python backend/knowledge/ingest.py
```

---

## langchain.text_splitter 导入失败

**现象**：`ModuleNotFoundError: No module named 'langchain.text_splitter'`

**原因**：langchain 1.2 将 text_splitter 独立为 `langchain-text-splitters` 包，导入路径变更为 `langchain_text_splitters`

**解决**：
```bash
pip install langchain-text-splitters
```
代码中改用 `from langchain_text_splitters import RecursiveCharacterTextSplitter`

---

## 后端模块导入失败（绝对导入 vs 相对导入）

**现象**：`uvicorn backend.main:app` 启动后报 `ModuleNotFoundError: No module named 'config'`

**原因**：`main.py` 使用 `from config import ...` 绝对导入，uvicorn 以 `backend.main` 为模块入口时 Python 路径解析不到 `backend/` 内的子模块

**解决**：
1. 添加 `backend/__init__.py` 使其成为正式 Python 包
2. 所有模块内导入改为相对导入：
   - `from .config import ...`（main.py → config.py）
   - `from ..config import ...`（routers/ → config.py）
   - `from ..services.xxx import ...`（routers/ → services/）

---

## DeepSeek API 响应格式不兼容

**现象**：`POST /api/chat` 返回 Pydantic 校验错误：
```
ValidationError: answer Input should be a valid string
[input_value=[{'type': 'text', 'text': '...'}]]
```

**原因**：DeepSeek 的 Anthropic 兼容接口返回 `response.content` 为 `list[dict]`（content blocks 格式），而标准 Anthropic API 返回纯字符串。Pydantic 的 `ChatResponse.answer: str` 校验失败。

**解决**：在 `generate_node()` 中添加格式适配：
```python
if isinstance(content, list):
    answer = "".join(block.get("text", "") for block in content)
else:
    answer = str(content)
```

---

## v2 相关性阈值设置错误

**现象**：v2 测试中所有问题的 `is_relevant` 都为 `False`，全部走了 `generate_uncertain` 路径

**原因**：假设 ChromaDB 使用余弦距离（范围 [0, 2]），阈值设为 1.0。但 ChromaDB 默认使用 L2 欧几里得距离，384 维向量的实际距离范围为 5-17。导致所有查询都被误判为不相关。

**解决**：基于实测数据校准阈值：
- 相关查询距离：5.5 - 8.0
- 无关查询距离：13.5+
- 阈值设为 10.0

---

## v2 改写可能降低精确问题的检索质量

**现象**：v2 将 "海龟交易法则的入市策略是什么？" 改写为 "海龟交易法则 入市 策略 突破 做多 做空" 后，检索来源从 p238（正确答案页）变为 p9（目录页），回答质量下降

**原因**：改写添加了 "突破 做多 做空" 等关键词，改变了语义重心，导致向量检索偏向不同方向

**解决**：v3 方案——先评估问题是否已精确，精确则跳过改写步骤

---

## uvicorn 启动目录错误

**现象**：从 `/stock/` 目录执行 `uvicorn backend.main:app` 报 `ModuleNotFoundError: No module named 'backend'`

**原因**：`backend` 包在 `stock_website/` 目录下，uvicorn 需要在包含 `backend/` 的目录中运行，Python 才能找到该模块

**解决**：
```bash
cd /Users/hrq/Coding/stock/stock_website
.stock/bin/python -m uvicorn backend.main:app --reload --port 8000
```

---

## 前后端分离重构后路径注意事项

- 前端文件位于 `frontend/`，后端通过 `config.py` 的 `STATIC_DIR = PROJECT_ROOT / "frontend"` 托管
- 前端页面中的资源引用（CSS/JS）使用绝对路径如 `/css/styles.css`、`/js/app.js`，不受目录名变更影响
- `schemas.py` 存放所有 Pydantic 请求/响应模型，新增 API 时应先在 schemas.py 中定义模型，再在 routers 中引用

---

## 反向代理 `<base>` 标签方案注意事项

- `<base>` 标签只影响**相对路径**（`/css/main.css`），不影响绝对 URL（`https://...`）和协议相对 URL（`//cdn.example.com/...`）
- 如果页面已有 `<base>` 标签，需用正则替换而非重复插入（`services/proxy.py` 已处理）
- Guardian CDN 资源（`assets.guim.co.uk`、`i.guim.co.uk`）使用绝对 URL，不受 `<base>` 影响，浏览器直接请求
- 域名白名单仅校验 `netloc`（`www.theguardian.com`），不含子域名变体；如需支持 `amp.theguardian.com` 等，应在白名单中追加
