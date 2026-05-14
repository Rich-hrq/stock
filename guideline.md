# 代码知识讲解 & 数据流 Pipeline

本文档帮助理解项目中各技术栈的用途、核心代码逻辑，以及从用户请求到数据返回的完整链路。

---

## 一、从请求发起到获得数据的完整 Pipeline

### Pipeline A：指数分析页面

```
用户打开页面（http://localhost:8000）
    │
    ├─ 1. FastAPI 返回 frontend/index.html（通过 StaticFiles 托管）
    │       前端加载 ECharts CDN 和各 JS 模块
    │
    ├─ 2. app.js 初始化 → GET /api/indices
    │       返回 [{symbol: "^GSPC", name: "标普500"}, ...]
    │       渲染指数标签和默认时间范围（6个月）
    │
    ├─ 3. app.js → GET /api/indices/^GSPC/analysis?start_date=...&end_date=...
    │       │
    │       ├─ routers/index_data.py: 接收请求，校验参数
    │       │
    │       ├─ services/market_data.py: fetch_index_data()
    │       │   ├─ 设置代理（all_proxy，因国内无法直连 Yahoo）
    │       │   ├─ 自动选择数据粒度（≤7天用1h，否则用1d）
    │       │   ├─ yfinance.Ticker(symbol).history(start, end, interval)
    │       │   └─ 返回 DataFrame（列名统一小写：open/high/low/close/volume）
    │       │
    │       ├─ services/indicators.py: 
    │       │   ├─ compute_bollinger()  → MA20 ± 2σ
    │       │   ├─ compute_atr()        → 20日真实波幅均值
    │       │   ├─ compute_donchian()   → 20/55日唐奇安通道
    │       │   ├─ judge_trend()        → 价格 vs 唐奇安通道判断趋势
    │       │   └─ generate_advice()    → 综合建议文案
    │       │
    │       └─ routers/index_data.py: 组装 JSON 返回
    │           { symbol, name, data[], stats, advice }
    │
    ├─ 4. charts.js: renderChart(data)
    │       ECharts 渲染 K线图 + 布林带 + 唐奇安通道 + 成交量
    │
    └─ 5. indicators.js: renderIndicators(data)
            渲染统计面板（起价/收价/涨跌幅/振幅）
            渲染海龟指标（ATR/N值/布林三轨/唐奇安上下轨）
            渲染投资建议文案
```

### Pipeline B：RAG 对话

```
用户在聊天框输入问题（例："什么是海龟交易法则的入市策略？"）
    │
    ├─ 1. chat.js → POST /api/chat  { message, history }
    │
    ├─ 2. routers/chat.py: 接收请求
    │
    ├─ 3. services/rag_v3.py: ask_question_v3()
    │       │
    │       ├─ evaluate_node: 判断问题是否已精确
    │       │   ├─ 精确 → 跳过扩展，直接用原问题检索
    │       │   └─ 不精确 → expand_node: 生成 2-3 个专业同义转述
    │       │
    │       ├─ retrieve_node: 多查询融合检索
    │       │   ├─ 用所有查询分别检索 ChromaDB
    │       │   ├─ 合并去重，按距离排序
    │       │   └─ 返回 top-4 最相关文本块
    │       │
    │       └─ generate_node:
    │           ├─ 组装 Prompt：检索到的原文 + 历史对话 + 用户问题
    │           ├─ ChatAnthropic (兼容 Claude / DeepSeek).invoke(prompt)
    │           └─ 返回 answer（严格基于书中原文）
    │
    └─ 4. chat.js: 渲染回答 + 来源页码引用
            更新对话历史（保留最近20条）
```

### Pipeline C：知识库构建（一次性）

```
运行 python backend/knowledge/ingest.py
    │
    ├─ 1. fitz.open("海龟交易法则.pdf")
    │       逐页提取文本，过滤空页
    │
    ├─ 2. RecursiveCharacterTextSplitter(chunk_size=500, overlap=50)
    │       按句号、换行等分隔符递归切分，保证语义完整性
    │       跳过短于20字符的片段
    │
    ├─ 3. SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    │       将每个文本块编码为 384 维向量
    │
    └─ 4. ChromaDB PersistentClient → collection.add()
            持久化到 backend/knowledge/chroma_db/
            后续启动无需重新索引
```

### Pipeline D：Polymarket 预测市场数据

```
用户发送预测查询（POST /api/predict  { keywords, limit, threshold }）
    │
    ├─ 1. routers/prediction.py: 接收请求，Pydantic 校验参数
    │       PredictRequest(keywords, limit, threshold)
    │
    ├─ 2. services/polymarket.py: fetch_polymarket_data()
    │       │
    │       ├─ 组装查询参数：limit / active / closed / volume_min
    │       ├─ 通过代理请求 Polymarket Gamma API
    │       │     GET https://gamma-api.polymarket.com/events
    │       │
    │       ├─ 遍历返回的 events，对每个 event：
    │       │     ├─ 提取 title + description + metadata.context_description 作为 context
    │       │     ├─ check_relevant(context, keywords): 检测关键词匹配
    │       │     └─ 匹配成功 → extract(event): 提取核心字段
    │       │
    │       └─ 返回 list[dict]：每个元素包含 title / description / markets[] / meta
    │
    └─ 3. routers/prediction.py: 返回 JSON 给前端
            如 API 请求失败 → 返回 502 + 错误详情
```

**Polymarket API 说明**：
- Gamma API (`gamma-api.polymarket.com`) 是 Polymarket 的公开数据接口，无需 API Key
- `active=true&closed=false`：只取活跃中的事件
- `volume_min`：过滤低交易量事件（单位：美元）
- 返回的 `markets[].outcomePrices` 是 JSON 字符串数组，需前端自行解析

**关键词过滤逻辑** (`check_relevant`)：
```python
# 大小写不敏感的包含匹配
# 只要 context（标题+描述+元数据）中包含任意一个 keyword，即返回 True
for k in keywords:
    for c in context:
        if k.lower() in c.lower():
            return True
return False
```

---

## 二、核心技术点讲解

### 1. FastAPI 的路由与 Pydantic 模型

```python
# 路由通过 APIRouter 组织，按功能分模块
router = APIRouter(prefix="/api/indices", tags=["indices"])

@router.get("/{symbol}/analysis")
async def get_index_analysis(...):  # async 允许并发处理请求
    ...
```

- `APIRouter`：将相关接口分组，挂载到 `app.include_router()`
- `async def`：FastAPI 原生支持异步，等待 I/O（网络请求/数据库查询）时不阻塞其他请求
- `Query()` 参数自动生成 OpenAPI 文档

**Pydantic 模型与 schemas.py**：

本项目将所有 API 的请求/响应模型统一存放在 `backend/schemas.py` 中：

```python
# schemas.py — 接口格式的"单一真相来源"
from pydantic import BaseModel

class ChatRequest(BaseModel):
    message: str
    history: list[dict] | None = None

class ChatResponse(BaseModel):
    answer: str
    sources: list[dict]
```

路由器通过相对导入引用：
```python
from ..schemas import ChatRequest, ChatResponse

@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    ...
```

这样设计的好处：
- **统一管理**：所有接口格式在一处定义，便于查阅和维护
- **前后端约定清晰**：前端只需看 `schemas.py` 即可了解所有 API 的请求/响应格式
- **自动校验与文档**：FastAPI 自动根据 Pydantic 模型生成 JSON Schema 和 Swagger 文档
- **减少重复**：避免在多个 router 文件中分散定义模型

### 2. yfinance 数据获取

```python
# yfinance 是对 Yahoo Finance 的 Python 封装，无需 API Key
raw = yf.Ticker("^GSPC").history(start="2026-01-01", end="2026-05-12", interval="1d")
# 返回 DataFrame: [Open, High, Low, Close, Volume, Dividends, Stock Splits]
```

关键注意点：
- 国内网络需设置代理 `all_proxy=http://127.0.0.1:7897`
- `end` 参数不包含当天，需 +1 天
- 时区问题：`raw.index.tz_localize(None)` 去掉时区，方便 JSON 序列化

### 3. 布林带 (Bollinger Bands)

```
中轨 = MA(close, 20)
上轨 = 中轨 + 2 × std(close, 20)
下轨 = 中轨 - 2 × std(close, 20)
```

- 带宽反映波动大小：越宽波动越大
- 统计学上约 95% 的价格落在带内（正态分布假设）
- 价格触上轨 → 可能超买；价格触下轨 → 可能超卖

### 4. ATR / N值 (Average True Range)

```
TR = max(H-L, |H-C_prev|, |L-C_prev|)   # 真实波幅
ATR = MA(TR, 20)                        # N值
```

海龟交易法则核心用法：
- **头寸规模**：1 Unit = 账户权益的 1% / N
- **止损**：海龟止损点 = 入场价 - 2N
- **加仓**：价格每上涨 0.5N，可增加一个单位（最多4单位）

### 5. 唐奇安通道 (Donchian Channel)

```
系统1（短期）：
  上轨 = max(high, 20)   → 突破做多
  下轨 = min(low, 10)    → 跌破平仓

系统2（长期）：
  上轨 = max(high, 55)   → 突破做多（更可靠但较迟钝）
  下轨 = min(low, 20)    → 跌破平仓
```

这是海龟交易法则最核心的入市策略，比布林带更直接——价格突破 N 日高点就买，跌破 N 日低点就卖。

### 6. LangGraph 状态图

```python
class RAGState(TypedDict):    # 定义图的"共享内存"
    question: str             # 用户问题
    context: list[str]        # 检索到的上下文
    answer: str               # 生成的回答

graph = StateGraph(RAGState)
graph.add_node("retrieve", retrieve_node)   # 节点1：检索
graph.add_node("generate", generate_node)   # 节点2：生成
graph.add_edge("retrieve", "generate")      # 串联
graph.add_edge("generate", END)
rag_app = graph.compile()                   # 编译为可执行的 App
```

LangGraph 相比直接调用的优势：
- 状态管理清晰，所有中间数据在 State 中传递
- 可扩展（例如加入 rewrite 节点重写问题、feedback 节点检查答案质量）
- 天然支持流式输出、checkpoint 等高级特性

### 7. RAG 检索增强生成

```
问题："海龟的入市策略是什么？"
  → SentenceTransformer 编码为向量 [0.12, -0.34, 0.56, ...]
  → ChromaDB 余弦相似度搜索，找到最相似的4个文本块
  → Prompt = 指令 + 原文(context) + 历史对话 + 用户问题
  → Claude 生成仅基于原文的回答
```

**为什么不用通用知识库？** 通用 LLM 对海龟交易法则的了解可能不准确或不完整。RAG 让模型严格基于原书回答，避免编造。

### 10. RAG 版本演进：v1 → v2 → v3

本项目实际经历了三次 RAG 流水线迭代，值得作为案例理解：

| 版本 | 流程 | 优点 | 问题 |
|------|------|------|------|
| v1 | `retrieve → generate` | 简单直接，延迟低 | 口语化问题检索质量差 |
| v2 | `rewrite → retrieve → judge → 条件路由` | 口语化问题改善，不确定回答有免责声明 | 对已精确的问题改写反而破坏检索；回环逻辑增加延迟 |
| v3 | `evaluate → [扩展/跳过] → 多查询融合检索 → generate` | **先判断再决定是否扩展**，精确问题零额外开销；多查询融合提高召回率 | |

**v3 的核心洞察**：
- 不是所有问题都需要改写——"海龟入市策略"不需要，"止损咋设的"需要
- 多查询合并检索 > 单一改写查询（多个角度同时搜索，互补盲区）
- 去掉回环逻辑，降低延迟和 LLM 调用成本

### 11. ChromaDB 向量数据库

```python
# 存储
collection.add(
    ids=["chunk_0", "chunk_1", ...],
    documents=["文本块1...", "文本块2...", ...],
    metadatas=[{"page": 1}, {"page": 2}, ...],
    embeddings=[[0.1, 0.2, ...], [0.3, 0.4, ...]],
)

# 检索
results = collection.query(
    query_embeddings=[[0.12, -0.34, ...]],
    n_results=4,
)
```

- 持久化存储，重启不丢失
- 余弦相似度为默认距离度量
- 轻量级，无需额外服务、适用于小规模知识库

### 9. ECharts 图表渲染

```javascript
option = {
    series: [
        { name: "布林带", type: "line", ... },     // 先绘制，在底层
        { name: "唐奇安通道", type: "line", ... }, // 中层
        { name: "K线", type: "candlestick", ... }, // 最上层
    ]
};
chart.setOption(option);
```

- `candlestick` 类型直接支持 OHLC 数据
- 多系列叠加实现布林带 + 唐奇安通道与 K 线共存
- `axisPointer: { type: "cross" }` 实现十字光标交互

### Pipeline E：The Guardian 新闻抓取

```
用户打开新闻页面（http://localhost:8000/news.html）或点击「获取新闻」
    │
    ├─ 1. news.js 页面加载时自动调用 POST /api/guardian_news
    │
    ├─ 2. routers/guardian.py: 接收请求
    │
    ├─ 3. services/guardian_news.py: scrape_guardian_news()
    │       │
    │       ├─ 通过代理请求 https://www.theguardian.com/us
    │       ├─ BeautifulSoup HTML 解析
    │       ├─ 遍历所有 <a> 标签，提取 href + 文本
    │       ├─ 过滤规则：
    │       │   ├─ 标题长度 10-200 字符
    │       │   ├─ 排除功能页链接（/preference/ /signin /subscribe 等）
    │       │   └─ 只保留链接中包含当前年份（如 /2026/）的新闻
    │       ├─ 去重（按 link 去重）
    │       └─ 返回 [{title, link}, ...]
    │
    └─ 4. news.js: renderNews(items)
            ├─ 从每个 item.link 提取分类: link.split("/")[3]
            ├─ 渲染分类标签：【CATEGORY】橙色徽章
            ├─ 渲染标题 + 编号
            └─ 渲染"查看原文"外链按钮（target="_blank"）
```

**分类提取逻辑**：
```javascript
// 例: https://www.theguardian.com/world/2026/may/14/some-article
// parts = ["https:", "", "www.theguardian.com", "world", "2026", "may", "14", "..."]
// parts[3] = "world" → 显示为 【WORLD】
const parts = item.link.split("/");
const category = parts.length > 3 ? parts[3] : "";
```

### 10. Polymarket 预测市场

```python
# Gamma API 是 Polymarket 的公开数据接口，无需 API Key
url = "https://gamma-api.polymarket.com/events"
params = {"limit": 500, "active": "true", "closed": "false", "volume_min": 100000}
response = requests.get(url, params=params, proxies={"http": proxy, "https": proxy})
```

- 每个事件包含多个子市场（markets），每个市场有不同的到期日和赔率
- `outcomePrices` 是 JSON 字符串（如 `["0.12", "0.88"]`），表示各结果当前隐含概率
- `volume` 是美元计价的累计交易量，用于判断市场活跃度
- 国内访问需设置代理，与 yfinance 共用 `HTTP_PROXY` 配置

### 11. BeautifulSoup 网页爬虫

```python
# BeautifulSoup 将 HTML 文本解析为 DOM 树，支持 CSS 选择器风格的查找
soup = BeautifulSoup(response.text, "html.parser")

# 提取所有 <a> 标签（超链接）
for article in soup.find_all("a", href=True):
    href = article.get("href")       # 链接地址
    title = article.get_text(strip=True)  # 链接的可见文本（去掉空白）
```

关键注意点：
- `get_text(strip=True)` 获取 `<a>` 标签内的纯文本，但可能包含 The Guardian 的版块标签（如 `Full report</span>Xi warns Trump...`），导致标题前缀不干净
- 链接可能是相对路径（如 `/world/2026/...`），需补全为绝对 URL
- 新闻链接的 URL 路径格式：`/section/year/month/day/slug`，其中 `section`（parts[3]）即分类名，前端据此生成 `【SECTION】` 标签
- `response.raise_for_status()` 在 HTTP 状态码非 2xx 时抛出异常，实现统一错误处理
