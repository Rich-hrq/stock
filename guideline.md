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
    │       │   ├─ auto_interval: 同日(start==end)用1h，跨日用1d
    │       │   │   （日线数据与 Yahoo Finance 网页端 OHLC 完全一致）
    │       │   ├─ yfinance.Ticker(symbol).history(start, end, interval)
    │       │   └─ 返回 DataFrame（列名统一小写：open/high/low/close/volume）
    │       │
    │       ├─ 额外获取前日收盘：fetch_index_data(prev_start, end, "1d")
    │       │   取 df_daily["close"].iloc[-2] 作为前日收盘
    │       │   用于计算日涨跌 (P→C) = (收价−前收)/前收，与 Yahoo Finance 对齐
    │       │
    │       ├─ services/indicators.py: 
    │       │   ├─ compute_bollinger()  → MA20 ± 2σ
    │       │   ├─ compute_atr()        → 20日真实波幅均值
    │       │   ├─ compute_ma()         → 简单移动均线 (MA5, MA10)
    │       │   ├─ compute_donchian()   → 20/55日唐奇安通道
    │       │   ├─ judge_trend()        → 价格 vs 唐奇安通道判断趋势
    │       │   └─ generate_advice()    → 综合建议文案
    │       │
    │       └─ routers/index_data.py: 组装 JSON 返回
    │           ├─ 数据记录合并：按位置（iloc[i]）对齐，不依赖日期字符串
    │           │  所有 DataFrame 共享同一 index，避免小时级 K 线互相覆盖
    │           ├─ stats 含 起价/收价/最高价/最低价/区间涨跌/日涨跌/前日收盘/振幅/趋势
    │           └─ { symbol, name, data[]（含ma5/ma10字段）, stats, advice }
    │
    ├─ 4. charts.js: renderChart(data)
    │       │
    │       ├─ 从 data[] 提取各系列数据（走势线/MA5/MA10/MA20/布林/唐奇安/OHLC/成交量）
    │       ├─ 按分组缓存 series 定义：price / ma / candlestick / bollinger / donchian
    │       ├─ 根据 groupState 拼装可见 series 数组 → applyVisibility()
    │       ├─ 图表上方 5 个切换按钮：
    │       │   [走势线 ·]  [均线 ✓]  [K线+量]  [布林带]  [唐奇安]
    │       │   走势线始终开启，其他可点击切换显隐
    │       ├─ 动态内联图例：● 彩色圆点 + 系列名（按当前可见分组实时更新）
    │       ├─ 日期格式化：同日数据显示 HH:MM，多日显示 YYYY-MM-DD
    │       ├─ 悬浮提示：按可见系列动态显示对应数值
    │       └─ MA20 系列被均线和布林带两组共享引用，两组同开时去重不重复绘制
    │
    └─ 5. indicators.js: renderIndicators(data)
            渲染统计面板（起始价/当前价/最高价/最低价/区间涨跌/日涨跌/前日收盘/振幅）
            渲染海龟指标（ATR/N值/MA5/MA10/布林三轨/唐奇安上下轨）
            渲染投资建议文案
```

### Pipeline J：K线形态识别（点击触发）

```
用户激活「K线+量」切换按钮 → groupState.candlestick = true
    │
用户点击图表中某根 K 线柱
    │
    ├─ 1. ECharts click 事件（seriesType === "candlestick"）
    │       charts.js 在 getChart() 中注册一次性 click handler
    │       检查：groupState.candlestick 为 true 且 seriesType 为 candlestick
    │
    ├─ 2. candlestick.js: analyzeCandlestick(records, dataIndex)
    │       │
    │       ├─ console.log 输出诊断信息（OHLC/实体/波幅/趋势判断）
    │       │
    │       ├─ 单根形态检测（始终执行）：
    │       │   ├─ detectHammer()        → 下跌趋势 + 小实体 + 长下影线
    │       │   ├─ detectHangingMan()    → 上涨趋势 + 小实体 + 长下影线
    │       │   └─ detectDoji()          → 实体≤15%波幅，4种变体分类
    │       │
    │       ├─ 多根形态检测（idx≥4 时执行）：
    │       │   ├─ detectBullishEngulfing() / detectBearishEngulfing()
    │       │   ├─ detectMorningStar() / detectEveningStar()
    │       │   ├─ detectRisingThreeMethods() / detectFallingThreeMethods()
    │       │   ├─ detectThreeBlackCrows() / detectThreeWhiteSoldiers()
    │       │   └─ detectIslandReversal()        → 跳空缺口检测
    │       │
    │       └─ 按可靠性星级降序排序结果
    │
    └─ 3. candlestick.js: showCandlestickPopup(results, dateStr)
            ├─ 无命中 → 显示「未检测到明显形态」提示
            ├─ 有命中 → 逐条渲染形态卡片（名称/英文名/星级/分类/完整讲解）
            └─ 关闭方式：✕按钮 / 关闭按钮 / 点击遮罩 / Esc 键
```

**检测辅助函数**：
- `isDowntrend()` / `isUptrend()`：5 日 lookback，优先 MA20 斜率 → 收盘价斜率 → 首尾比较 fallback
- `isSmallBody()` / `isBigBody()`：相对近 20 日平均实体判定
- `bodyLen()` / `upperShadow()` / `lowerShadow()` / `totalRange()`：单根 K 线形态计算
- `slope()`：跳过 null 值的简单线性回归斜率

**讲解文案**：每种形态内置完整中文讲解（形态特征 / 原理 / 出现位置 / 可靠性评级 / 确认信号 / 止损建议 / 增强因素），来源于 12 种经典 K 线形态教材。```

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
            响应含 v3 元数据：is_precise / search_queries / avg_distance
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

项目提供两种搜索模式，前端通过模式切换按钮选择：

#### 搜索模式（默认，调用 `/public-search`）

```
用户输入关键词 → POST /api/predict/search  { query, limit_per_type, threshold }
    │
    ├─ 1. routers/prediction.py: 接收请求，Pydantic 校验参数
    │       PredictSearchRequest(query, limit_per_type, threshold)
    │
    ├─ 2. services/polymarket.py: search_polymarket_events()
    │       │
    │       ├─ 组装查询参数：q=query, limit_per_type
    │       ├─ 通过代理请求 Polymarket 搜索 API
    │       │     GET https://gamma-api.polymarket.com/public-search?q=...&limit_per_type=...
    │       │
    │       ├─ 从响应中取 data["events"] 列表
    │       ├─ 本地过滤：跳过 volume < threshold 的 event
    │       └─ extract(event) 格式化 → 返回 list[dict]
    │
    └─ 3. routers/prediction.py: 返回 JSON 给前端
            如 API 请求失败 → 返回 502 + 错误详情
```

#### 列表模式（原有，调用 `/events`）

```
用户输入关键词 → POST /api/predict  { keywords, limit, threshold }
    │
    ├─ 1. routers/prediction.py: 接收请求，Pydantic 校验参数
    │       PredictRequest(keywords, limit, threshold)
    │
    ├─ 2. services/polymarket.py: fetch_polymarket_data()
    │       │
    │       ├─ 组装查询参数：limit / active / closed / volume_min
    │       ├─ 通过代理请求 Polymarket 事件列表 API
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

#### 两种模式对比

| 维度 | 搜索模式 | 列表模式 |
|------|---------|---------|
| **API 端点** | `GET /public-search?q=...` | `GET /events?active=true&closed=false&volume_min=...` |
| **前端路由** | `POST /api/predict/search` | `POST /api/predict` |
| **关键词过滤** | 服务端全文搜索引擎匹配（与官网搜索一致） | 本地 `check_relevant()` 大小写不敏感包含匹配 |
| **volume 过滤** | 搜索后本地过滤（API 不支持 `volume_min`） | API 端 `volume_min` 参数直接过滤 |
| **返回上限** | `limit_per_type`（默认 20） | `limit`（传入 500，API 实际限制 100） |
| **数据获取方式** | 精准搜索，直接返回匹配项 | 遍历全量列表，客户端筛选 |
| **优势** | 快速精准，可搜到官方搜索引擎索引到的所有事件 | 无搜索 API 依赖，可获取较完整的活跃事件 |
| **劣势** | 不支持 `volume_min` 服务端过滤 | 默认排序不在前 100 的事件会被遗漏；需自己分页 |

**实际案例**：搜索 `"iran"` 查找 `"US x Iran permanent peace deal by...?"`（volume 1.28 亿）
- 搜索模式：`GET /public-search?q=iran` → 直接命中 ✅
- 列表模式：`GET /events?limit=500&volume_min=100000` → 服务端只返回前 100 条，且默认排序（非 volume）下该事件排不进前 100 ❌

**Polymarket API 通用说明**：
- Gamma API (`gamma-api.polymarket.com`) 是 Polymarket 的公开数据接口，无需 API Key
- 返回的 `markets[].outcomePrices` 是 JSON 字符串数组，需前端自行解析
- 国内访问需设置代理，与 yfinance 共用 `HTTP_PROXY` 配置

**关键词过滤逻辑** (`check_relevant`，仅列表模式)：
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
    history: list[dict] | None = None  # [{role, content}, ...]

class ChatResponse(BaseModel):
    answer: str
    sources: list[dict]
    # v3 额外字段
    is_precise: bool | None = None          # 问题是否被判定为精确（跳过扩展）
    search_queries: list[str] | None = None  # 实际使用的检索查询列表
    avg_distance: float | None = None        # 检索结果的平均向量距离

class PredictRequest(BaseModel):
    """预测市场查询请求（列表模式）"""
    keywords: list[str] = ["nasdaq", "s&p500", ...]
    limit: int = 500
    threshold: int = 100000

class PredictSearchRequest(BaseModel):
    """预测市场查询请求（搜索模式）"""
    query: str                           # 搜索关键字，空格分隔多个词
    limit_per_type: int = 20             # 每种实体类型返回上限
    threshold: int = 0                   # 成交量下限（本地过滤）

class NewsSummaryRequest(BaseModel):
    headlines: list[dict]  # [{title, link}, ...]

class NewsSummaryResponse(BaseModel):
    summary: str
    generated_at: str
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

### 8. RAG 版本演进：v1 → v2 → v3

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

### 9. ChromaDB 向量数据库

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

### 10. ECharts 图表渲染

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
    └─ 4. news.js: renderNews(items) + fetchAISummary(items)
            ├─ 从每个 item.link 提取分类: link.split("/")[3]
            ├─ 渲染分类标签：【CATEGORY】橙色徽章
            ├─ 渲染标题 + 编号
            ├─ 渲染"查看原文"按钮（href="/api/proxy?url=..."）
            └─ 调用 POST /api/news/summary → 见 Pipeline G
```

**分类提取逻辑**：
```javascript
// 例: https://www.theguardian.com/world/2026/may/14/some-article
// parts = ["https:", "", "www.theguardian.com", "world", "2026", "may", "14", "..."]
// parts[3] = "world" → 显示为 【WORLD】
const parts = item.link.split("/");
const category = parts.length > 3 ? parts[3] : "";
```

### Pipeline F：Guardian 反向代理

```
用户点击新闻「查看原文」
    │
    ├─ 1. news.js: href="/api/proxy?url=${encodeURIComponent(item.link)}"
    │       新标签页打开
    │
    ├─ 2. routers/proxy.py: GET /api/proxy?url=...
    │       从 query string 提取 url 参数
    │
    ├─ 3. services/proxy.py: fetch_page(url)
    │       │
    │       ├─ urlparse(url).netloc → 域名白名单校验
    │       │   ├─ www.theguardian.com → 放行
    │       │   └─ 其他域名 → ValueError → 403 Forbidden
    │       │
    │       ├─ requests.get(url, headers, proxies) 通过代理请求 Guardian
    │       ├─ 注入 <base href="https://www.theguardian.com"> 到 <head>
    │       │   ├─ 页面已有 <base> → 用正则替换
    │       │   └─ 没有 → <head> 后插入
    │       └─ 返回修改后的 HTML
    │
    └─ 4. 浏览器收到 HTML
            ├─ <base> 标签生效，所有相对路径资源自动解析为 Guardian 绝对 URL
            ├─ CSS / JS / 图片由浏览器直接向 Guardian 请求（不走后端代理）
            └─ 用户看到完整的 Guardian 原始页面
```

**`<base>` 标签原理**：
```html
<!-- 后端注入到 <head> 中 -->
<base href="https://www.theguardian.com">

<!-- 页面中的相对路径 -->
<img src="/img/photo.jpg">
<!-- 浏览器自动解析为 https://www.theguardian.com/img/photo.jpg -->
```

这样后端只需代理 HTML 文档本身（几十到几百 KB），CSS/JS/图片等子资源由浏览器自行请求。

**安全设计 — 域名白名单**：
```python
parsed = urlparse(url)
if parsed.netloc != "www.theguardian.com":
    raise ValueError(f"不允许的域名: {parsed.netloc}")
```
- 防止被滥用为开放代理（别人用你的服务器访问任意网站）
- 防止 SSRF 攻击（访问 127.0.0.1、169.254.169.254 等内网地址）

### Pipeline G：AI 新闻摘要

```
页面加载 → /api/health（获取模型名并立即显示在摘要卡片头部）
    │
新闻列表渲染完成 → news.js 自动触发摘要生成
    │
    ├─ 1. news.js: fetchAISummary(items)
    │       POST /api/news/summary  { headlines: [{title, link}, ...] }
    │       失败时先检查 Content-Type：HTML → 诊断 nginx 504，JSON → 解析 error_reason
    │
    ├─ 2. routers/guardian.py: summarize_news()
    │       校验 headlines 非空
    │       try: generate_summary_async() → 返回 {summary, model, error_reason: ""}
    │       except SummaryError → 返回 {summary: "", model, error_reason: "apikey"/"timeout"/...}
    │
    ├─ 3. services/news_summary.py: 三层并发保护
    │       │
    │       ├─ asyncio.Semaphore(2)        ← 第一层：最多 2 个并发 LLM 调用
    │       ├─ asyncio.wait_for(50s)       ← 第二层：硬超时取消（nginx 120s 内有足够余量）
    │       └─ asyncio.to_thread(...)      ← 第三层：LLM 阻塞调用移出事件循环
    │              │
    │              ├─ MAX_HEADLINES=25：只取前 25 条标题（控制 prompt 长度）
    │              ├─ max_tokens=2048：减少生成耗时
    │              ├─ max_retries=0：不自动重试，由 wait_for 统一控制
    │              ├─ default_request_timeout=40s：单次 HTTP 请求超时
    │              │
    │              ├─ 提取分类标签 [world] / [business] → 组装 Prompt
    │              ├─ ChatAnthropic.invoke(prompt)
    │              │   └─ 每次调用重建实例（非单例），确保 model/api_key 最新
    │              ├─ _extract_answer(): 过滤 thinking block，只取 text
    │              └─ 异常 → _classify_and_raise() → SummaryError(apikey/timeout/ratelimit/model/network)
    │
    └─ 4. news.js: 渲染结果
            ├─ 成功：formatSummary(summary) → 渲染正文
            ├─ 失败：红色诊断面板展示具体原因 + 排查建议
            └─ 模型名始终可见（来自 /api/health，不依赖摘要接口）
```

**设计要点**：
- **并发控制**：`Semaphore(2)` 限制 LLM 并发，配合 `wait_for(50s)` 硬超时，防止线程池耗尽和 nginx 504
- **模型选择**：推荐 `deepseek-v4-flash`（29s/36标题），不推荐 `deepseek-v4-pro`（91s/36标题）
- **标题截断**：`MAX_HEADLINES=25` 平衡覆盖面与耗时
- **错误分类**：`SummaryError` 将 LLM 异常归为 6 类（apikey/timeout/ratelimit/model/network/unknown），前端据此展示对应排查建议
- **非单例 LLM**：`_get_llm()` 每次重建实例，确保 uvicorn auto-reload 后参数（模型名、API Key）始终最新
- **thinking block 兼容**：DeepSeek V4 返回 `[{type: "thinking", thinking: ...}, {type: "text", text: ...}]`，`_extract_answer()` 通过 `block.get("text", "")` 自动过滤
- **nginx 配合**：`/api/news/summary` 单独配置 `proxy_read_timeout 120s`，给 `wait_for(50s)` 留足余量

### 11. Polymarket 预测市场

项目提供两种搜索模式，通过前端模式切换按钮切换：

**搜索模式**（默认）— 调用 `GET /public-search` 端点：
```python
# 全文搜索引擎，与 Polymarket 官网搜索一致
url = "https://gamma-api.polymarket.com/public-search"
params = {"q": "iran peace", "limit_per_type": 20}
response = requests.get(url, params=params, proxies={"http": proxy, "https": proxy})
data = response.json()
events = data["events"]  # 搜索结果自动按相关性排序
```

**列表模式**（原有）— 调用 `GET /events` 端点：
```python
# 遍历事件列表，本地做关键词匹配
url = "https://gamma-api.polymarket.com/events"
params = {"limit": 500, "active": "true", "closed": "false", "volume_min": 100000}
response = requests.get(url, params=params, proxies={"http": proxy, "https": proxy})
# 对每个 event 做 check_relevant() 本地关键词过滤
```

两种模式的关键差异：
| 维度 | 搜索模式 | 列表模式 |
|------|---------|---------|
| API | `/public-search` | `/events` |
| 过滤 | API 端全文搜索 | 本地 `check_relevant()` |
| volume | 搜索后本地过滤 | API 端 `volume_min` |
| 结果上限 | `limit_per_type` | API 实际限制 100 条 |
| 适用 | 精准关键词搜索 | 全量浏览 |

- Gamma API (`gamma-api.polymarket.com`) 是 Polymarket 的公开数据接口，无需 API Key
- 每个事件包含多个子市场（markets），每个市场有不同的到期日和赔率
- `outcomePrices` 是 JSON 字符串（如 `["0.12", "0.88"]`），表示各结果当前隐含概率
- `volume` 是美元计价的累计交易量，用于判断市场活跃度
- 国内访问需设置代理，与 yfinance 共用 `HTTP_PROXY` 配置

### 12. BeautifulSoup 网页爬虫

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

### Pipeline H：持仓记录（注册/登录 + 交易 + 盈亏汇总）

```
用户打开持仓页面（http://localhost:8000/portfolio.html）
    │
    ├─ 1. portfolio.js 检查 localStorage 中的 JWT Token
    │       ├─ 有 Token → 调用 GET /api/auth/me 验证是否过期
    │       │              └─ 过期 → 清除 Token，显示登录表单
    │       └─ 无 Token → 显示登录/注册表单
    │
    ├─ 2. 注册流程：
    │       POST /api/auth/register  { username, password }
    │       │
    │       ├─ routers/auth.py: 校验（用户名 3-20 字符，密码 ≥6 位）
    │       ├─ 查重：SELECT FROM users WHERE username = ?
    │       │   └─ 已存在 → 409（用户名已存在）
    │       ├─ hash_password(): bcrypt.hashpw(password.encode(), gensalt())
    │       ├─ INSERT INTO users (username, password_hash, created_at)
    │       └─ 返回 JWT Token（7 天有效期，HS256 签名）
    │
    ├─ 3. 登录流程：
    │       POST /api/auth/login  { username, password }
    │       │
    │       ├─ routers/auth.py: 查询用户 → 不存在 → 401（用户名或密码错误）
    │       ├─ verify_password(): bcrypt.checkpw(plain.encode(), hashed.encode())
    │       │   └─ 不匹配 → 401
    │       └─ 返回 JWT Token
    │
    ├─ 4. 交易记录：
    │       POST /api/portfolio/transactions  { symbol, direction, trade_date, amount_cny }
    │       Header: Authorization: Bearer <token>
    │       │
    │       ├─ routers/portfolio.py: get_current_user() 解析 Token → 获取 User
    │       ├─ services/market_data.py: yfinance 查询交易日收盘价
    │       ├─ services/exchange_rate.py: open.er-api.com 查询当日 USD/CNY 汇率
    │       │   └─ 缓存 1 小时，避免频繁调用外部 API
    │       ├─ 计算：usd_equivalent = amount_cny / rate, shares = usd / close_price
    │       ├─ INSERT INTO transactions (...)
    │       └─ 返回完整交易记录
    │
    └─ 5. 持仓汇总：
            GET /api/portfolio/summary
            Header: Authorization: Bearer <token>
            │
            ├─ routers/portfolio.py: 查询该用户所有交易记录
            ├─ 按 symbol 分组，加权平均成本法计算：
            │   ├─ 买入 → 累加 shares 和 total_cost
            │   ├─ 卖出 → 按比例减少 shares，结算已实现盈亏
            │   └─ avg_cost = total_cost / shares
            ├─ 实时获取当前价（yfinance）+ 汇率（open.er-api.com）
            ├─ 计算未实现盈亏：liquidation_value - total_cost
            └─ 返回每只指数的 PositionSummary + 整体 PortfolioSummary
```

### Pipeline I：市场状态指示器

```
用户打开主页（http://localhost:8000）
    │
    ├─ 1. app.js DOMContentLoaded 后立即调用 fetchMarketStatus()
    │       GET /api/market/status（无需认证）
    │       └─ 之后每 30 秒 setInterval 自动轮询刷新
    │
    ├─ 2. routers/market_status.py: GET /api/market/status
    │       调用 services/market_status.py 的 get_market_status()
    │
    ├─ 3. services/market_status.py: get_market_status()
    │       │
    │       ├─ 获取 UTC 当前时间 → 转换为美东时间（ET）
    │       │   └─ _et_offset(date): 计算给定日期的 UTC 偏移
    │       │       ├─ 夏令时 EDT (3月第二个周日 ~ 11月第一个周日): UTC-4
    │       │       └─ 冬令时 EST (其余时间): UTC-5
    │       │
    │       ├─ 判断交易时段（按美东时间）：
    │       │   ├─ 周末（周六/日）→ status="closed", "周末休市"
    │       │   ├─ 00:00~04:00   → status="closed", "已收盘"（等当天盘前）
    │       │   ├─ 04:00~09:30   → status="pre_market", "盘前交易"
    │       │   ├─ 09:30~16:00   → status="open", "开盘中"
    │       │   ├─ 16:00~20:00   → status="after_hours", "盘后交易"
    │       │   └─ 20:00~24:00   → status="closed", "已收盘"（等下一交易日）
    │       │
    │       ├─ 计算下次开盘/收盘时间（自动跳过周末）
    │       │   └─ _next_trading_day(date): 跳过周六/日，返回下周一
    │       │
    │       └─ 双时区格式化：
    │           ├─ _fmt_et(dt): → "2026-05-18 09:30 EDT"（自动标注 EDT/EST）
    │           └─ _fmt_cn(dt): → "2026-05-18 21:30 CST"（UTC+8 固定偏移）
    │
    └─ 4. app.js: renderMarketStatus(el, data)
            ├─ 状态指示圆点：绿色呼吸(开盘中) / 橙色(盘前/盘后) / 灰色(休市) / 红色(未知)
            ├─ 状态标签文字：data.status_text（如"开盘中"）
            ├─ 显示下一次事件时间（北京）：data.next_event_time_cn
            └─ 鼠标悬停 tooltip：同时显示美东和北京双时区信息
```

**API 响应示例**：

```json
{
  "status": "open",
  "status_text": "开盘中",
  "status_text_en": "Market Open",
  "current_et": "2026-05-18 10:30 EDT",
  "current_cn": "2026-05-18 22:30 CST",
  "next_event": "close",
  "next_event_time_et": "2026-05-18 16:00 EDT",
  "next_event_time_cn": "2026-05-19 04:00 CST",
  "next_event_label": "收盘",
  "next_event_label_en": "Market Close"
}
```

**自动刷新机制**：
- 页面加载时立即请求一次
- `setInterval(fetchMarketStatus, 30000)` 每 30 秒轮询
- 无需用户手动刷新，状态实时更新

### 13. MySQL 数据库设计

#### 13.1 数据库连接与配置

数据库配置通过 `backend/.env` 文件管理，`python-dotenv` 在应用启动时自动加载：

```
MYSQL_HOST=127.0.0.1
MYSQL_USER=stock
MYSQL_PASSWORD=12345abcde@stock
MYSQL_DATABASE=stock
```

`backend/config.py` 读取环境变量并暴露为模块常量：

```python
MYSQL_HOST = os.environ.get("MYSQL_HOST", "")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "stock")
```

**条件启动**：`MYSQL_HOST` 为空时跳过数据库初始化，指数分析/RAG/新闻等功能不受影响。

#### 13.2 数据表结构

项目共有 **3 张表**，均通过 SQLAlchemy ORM 的 `Base.metadata.create_all` 自动创建（无手动 SQL 或 Alembic 迁移脚本）。

##### 表 1：`users` — 用户表

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | `INT` | `PRIMARY KEY`, `AUTO_INCREMENT` | 用户唯一标识 |
| `username` | `VARCHAR(20)` | `UNIQUE`, `NOT NULL` | 用户名 |
| `password_hash` | `VARCHAR(128)` | `NOT NULL` | bcrypt 加密密码哈希 |
| `created_at` | `DATETIME` | `DEFAULT NOW()` | 注册时间 |

隐式索引：`username` 的 UNIQUE 约束自动创建唯一索引。

##### 表 2：`investment_plans` — 定投计划表

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | `INT` | `PRIMARY KEY`, `AUTO_INCREMENT` | 计划唯一标识 |
| `user_id` | `INT` | `FOREIGN KEY → users.id` | 所属用户 |
| `symbol` | `VARCHAR(20)` | `NOT NULL` | 指数代码（如 ^GSPC） |
| `amount_cny` | `DECIMAL(12, 2)` | `NOT NULL` | 每次买入金额（人民币） |
| `frequency` | `VARCHAR(10)` | `NOT NULL` | 定投频率：`weekly` 或 `monthly` |
| `day_of_week` | `INT` | `NULL` | 每周几（0=周一..6=周日），仅 weekly 时有效 |
| `day_of_month` | `INT` | `NULL` | 每月几号（1-28），仅 monthly 时有效 |
| `enabled` | `TINYINT(1)` | `DEFAULT 1` | 是否启用（True/False） |
| `last_executed` | `DATE` | `NULL` | 上次执行日期，用于计算遗漏执行日 |
| `created_at` | `DATETIME` | `DEFAULT NOW()` | 创建时间 |

`frequency` 与 `day_of_*` 的互斥逻辑在后端路由层校验：
- `weekly` → 必须提供 `day_of_week`（0~6）
- `monthly` → 必须提供 `day_of_month`（1~28）

##### 表 3：`transactions` — 交易记录表

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | `INT` | `PRIMARY KEY`, `AUTO_INCREMENT` | 交易唯一标识 |
| `user_id` | `INT` | `FOREIGN KEY → users.id` | 所属用户 |
| `symbol` | `VARCHAR(20)` | `NOT NULL` | 指数代码（如 ^GSPC） |
| `direction` | `VARCHAR(4)` | `NOT NULL` | 方向：`buy` 或 `sell` |
| `trade_date` | `DATE` | `NOT NULL` | 交易日期 |
| `amount_cny` | `DECIMAL(12, 2)` | `NOT NULL` | 人民币金额（用户输入） |
| `close_price_usd` | `DECIMAL(10, 2)` | `NOT NULL` | 当日收盘价，美元（yfinance 自动查询） |
| `exchange_rate` | `DECIMAL(8, 4)` | `NOT NULL` | 当日 USD/CNY 汇率（open.er-api.com 自动查询） |
| `usd_equivalent` | `DECIMAL(12, 2)` | `NOT NULL` | 美元等值 = amount_cny / exchange_rate（计算字段） |
| `shares` | `DECIMAL(12, 6)` | `NOT NULL` | 持有份额 = usd_equivalent / close_price_usd（计算字段） |
| `created_at` | `DATETIME` | `DEFAULT NOW()` | 记录创建时间 |

**列的分工**：
- 用户只需输入 `symbol`、`direction`、`trade_date`、`amount_cny`
- `close_price_usd` 和 `exchange_rate` 由后端在创建交易时自动查询外部 API 获取
- `usd_equivalent` 和 `shares` 由后端根据前两者自动计算
- `created_at` 由数据库自动填充

**外键关系**：
```
investment_plans.user_id ──→ users.id
transactions.user_id     ──→ users.id
```
外键未设置 `ON DELETE CASCADE`，删除用户时若存在关联的交易或计划会触发外键错误。

#### 13.3 SQLAlchemy ORM 模型定义

所有模型定义在 `backend/models.py`，使用 SQLAlchemy 2.0 声明式映射（`Mapped` + `mapped_column`）：

```python
from sqlalchemy import ForeignKey, Numeric, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    """所有模型的基类。"""
    pass

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(20), unique=True, comment="用户名")
    password_hash: Mapped[str] = mapped_column(String(128), comment="bcrypt 加密密码")
    created_at: Mapped[datetime] = mapped_column(default=func.now(), comment="注册时间")

class InvestmentPlan(Base):
    __tablename__ = "investment_plans"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), comment="所属用户")
    symbol: Mapped[str] = mapped_column(String(20), comment="指数代码")
    amount_cny: Mapped[Decimal] = mapped_column(Numeric(12, 2), comment="每次买入金额")
    frequency: Mapped[str] = mapped_column(String(10), comment="weekly 或 monthly")
    day_of_week: Mapped[int | None] = mapped_column(nullable=True, comment="每周几")
    day_of_month: Mapped[int | None] = mapped_column(nullable=True, comment="每月几号")
    enabled: Mapped[bool] = mapped_column(default=True, comment="是否启用")
    last_executed: Mapped[date | None] = mapped_column(nullable=True, comment="上次执行日期")
    created_at: Mapped[datetime] = mapped_column(default=func.now(), comment="创建时间")

class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), comment="所属用户")
    symbol: Mapped[str] = mapped_column(String(20), comment="指数代码")
    direction: Mapped[str] = mapped_column(String(4), comment="buy 或 sell")
    trade_date: Mapped[date] = mapped_column(comment="交易日期")
    amount_cny: Mapped[Decimal] = mapped_column(Numeric(12, 2), comment="人民币金额")
    close_price_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2), comment="当日收盘价")
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(8, 4), comment="当日汇率")
    usd_equivalent: Mapped[Decimal] = mapped_column(Numeric(12, 2), comment="美元等值")
    shares: Mapped[Decimal] = mapped_column(Numeric(12, 6), comment="持有份额")
    created_at: Mapped[datetime] = mapped_column(default=func.now(), comment="记录创建时间")
```

**类型映射关系**：

| Python 类型 | SQLAlchemy 类型 | MySQL 列类型 |
|------------|----------------|-------------|
| `int` | `Integer` | `INT` |
| `str` | `String(n)` | `VARCHAR(n)` |
| `Decimal` | `Numeric(p, s)` | `DECIMAL(p, s)` |
| `date` | `Date` | `DATE` |
| `datetime` | `DateTime` | `DATETIME` |
| `bool` | `Boolean` | `TINYINT(1)` |

#### 13.4 异步引擎与会话管理

`backend/database.py` 负责创建异步引擎、会话工厂和依赖注入：

```python
from urllib.parse import quote_plus
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

def _build_url() -> str:
    """构建 MySQL 异步连接 URL，quote_plus 防止密码特殊字符破坏解析。"""
    user = quote_plus(MYSQL_USER)
    password = quote_plus(MYSQL_PASSWORD)
    return f"mysql+aiomysql://{user}:{password}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}?charset=utf8mb4"

engine = create_async_engine(
    _build_url(),
    echo=False,             # 不打印 SQL 日志
    pool_pre_ping=True,     # 连接检出前 ping 测试，断连自动重连
    pool_size=5,            # 常驻连接数
    max_overflow=10,        # 峰值可额外创建的连接数
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_db() -> None:
    """启动时自动创建所有表（如已存在则跳过）。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖注入：提供数据库会话，请求结束时自动关闭。"""
    async with async_session() as session:
        yield session
```

**关键设计点**：
- `quote_plus` 对用户名/密码进行百分号编码，防止 `@` `/` `:` 等字符破坏连接串解析（实际踩过密码含 `@` 导致解析错误的坑）
- `pool_pre_ping=True`：每次从连接池取出连接时先 ping，检测断连自动重连，适合 MySQL 默认 8 小时超时断开
- `pool_size=5, max_overflow=10`：常规 5 连接 + 峰值可额外 10 连接
- `expire_on_commit=False`：commit 后 ORM 对象不过期，可直接作为 Pydantic 响应返回
- `get_session()` 作为 FastAPI `Depends` 使用：请求进入时创建会话，请求结束时 `async with` 上下文自动关闭并归还连接池
- `init_db()` 在 `main.py` 的 `lifespan` 启动事件中调用，`create_all` 只创建不存在的表，不修改已有表结构（无迁移能力）

**表创建机制**：`Base.metadata.create_all` 通过检查 MySQL `information_schema` 判断表是否存在，存在则跳过。这意味着：
- 首次启动：自动建表
- 后续启动：跳过（不会修改表结构）
- 如需变更表结构，需手动执行 `ALTER TABLE` 或删除表后重建

### 14. JWT + bcrypt 认证

```python
# auth.py — 用户认证工具
import bcrypt
from jose import jwt

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))

def create_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=7)
    return jwt.encode({"sub": str(user_id), "exp": expire}, JWT_SECRET, algorithm="HS256")
```

技术选型说明：
- **bcrypt**：当前最安全的密码哈希算法之一，自带盐值、抗彩虹表、计算开销可调。本项目用 bcrypt 原生 API（避免 passlib 与 bcrypt 5.x 的兼容性问题）
- **JWT (HS256)**：对称签名，服务端用 `JWT_SECRET` 对 `{user_id, expire}` 签名，后续请求只需验签即可知道"是谁在请求"，无需查询 session
- **`get_current_user()`**：FastAPI `Depends`，从 `Authorization: Bearer <token>` 头解析 JWT → 查数据库 → 返回 User 对象
- **Token 7 天过期**：平衡安全性与用户体验，过期后需重新登录
- **`python-dotenv`**：在 `main.py` 启动时加载 `backend/.env`，避免每次手动设置环境变量

---

## 三、公网部署

将本地服务发布到公网有两种方式：**Cloudflare Tunnel**（无需公网 IP）和 **Nginx 直连**（需公网 IP）。本项目实际部署在 `stock.richhrq.xyz`，采用方案 A。

### Pipeline K：Cloudflare Tunnel 公网访问（无公网 IP）

这是本项目实际使用的部署方式。利用 Cloudflare Zero Trust 建立安全隧道，家宽/内网服务器无需公网 IP 即可被公网访问，同时自动获得 HTTPS 证书和 CDN 加速。

**完整架构**：

```
                                        局域网 (无公网 IP)
┌──────────┐    ┌──────────────┐    ┌──────────────────────────────┐
│  浏览器    │    │  Cloudflare  │    │  cloudflared    nginx     uvicorn│
│           │───→│  CDN/Edge    │───→│  (隧道客户端) ──→ :80 ──→ :8000  │
│ stock...  │    │  (HTTPS)     │    │                              │
│  .xyz     │    │              │    │  服务器/树莓派/家庭电脑         │
└──────────┘    └──────────────┘    └──────────────────────────────┘
     ↑                ↑                        ↑
  DNS 解析        自动 SSL                  出站连接到
  (CNAME →      (Edge Cert)              Cloudflare
  tunnel)                                (无需入站端口)
```

**请求全链路**：

```
1. 用户在浏览器输入 https://stock.richhrq.xyz/api/health

2. DNS 解析
   stock.richhrq.xyz → CNAME → <tunnel-id>.cfargotunnel.com → Cloudflare Edge

3. Cloudflare Edge
   ├─ SSL 终结（自动签发 Edge Certificate）
   ├─ CDN 缓存静态资源（可选）
   └─ 将请求通过 QUIC 隧道转发给 cloudflared

4. cloudflared（运行在本地服务器）
   ├─ 出站连接到 Cloudflare（只需 443 出站，无需开放入站端口）
   ├─ 收到隧道内的 HTTP 请求
   └─ 按 ingress 配置转发：hostname 匹配 → 转发到 http://localhost:80

5. Nginx (:80)
   ├─ 收到 cloudflared 转发来的请求
   ├─ proxy_pass http://127.0.0.1:8000
   └─ 添加 X-Real-IP / X-Forwarded-For 等头

6. uvicorn (:8000)
   ├─ 处理业务逻辑
   └─ 返回响应

7. 响应原路返回：uvicorn → nginx → cloudflared → Cloudflare → 浏览器
   （浏览器看到的是 HTTPS 加密的响应）
```

**关键设计点**：

| 环节 | 说明 |
|------|------|
| **隧道方向** | cloudflared **主动出站**连接 Cloudflare，不需要路由器端口转发、不需要公网 IP |
| **SSL 终结** | Cloudflare Edge 自动处理 HTTPS，本地 nginx 不需要配证书 |
| **防火墙友好** | cloudflared 只发起到 `*.argotunnel.com` 的 443 出站连接，无需开放任何入站端口 |
| **CDN 加速** | 静态资源（CSS/JS/图片）可由 Cloudflare CDN 缓存，减少回源流量 |
| **DDoS 防护** | Cloudflare 自带基础 DDoS 防护，攻击流量在 Edge 层面过滤 |
| **零信任** | 可配合 Cloudflare Access 添加身份验证（如 OTP / GitHub 登录），在到达应用前拦截未授权用户 |

**对比：有公网 IP 的部署方式**：

```
┌──────────┐    ┌──────────────────────────┐
│  浏览器    │───→│  公网 IP 服务器            │
│           │    │  nginx (:80/:443)        │
│           │    │    └─→ uvicorn (:8000)   │
└──────────┘    └──────────────────────────┘
```

| 维度 | Cloudflare Tunnel | 有公网 IP + Nginx |
|------|------------------|-------------------|
| **公网 IP** | 不需要 | 需要（VPS 或固定 IP 宽带） |
| **入站端口** | 0 个（纯出站连接） | 80/443 需对外开放 |
| **HTTPS 证书** | Cloudflare 自动签发 | 需手动配置 Let's Encrypt（certbot） |
| **DDoS 防护** | 自带 | 需自行配置 fail2ban / WAF |
| **延迟** | 多一跳（经过 Cloudflare Edge） | 直连，理论上更低 |
| **费用** | 免费（Cloudflare Free Plan） | 服务器/VPS 费用 |
| **适用场景** | 家庭宽带、内网服务器、树莓派 | VPS、云服务器、IDC 托管 |

**Cloudflared 操作步骤**：

#### 步骤 1：安装 cloudflared

```bash
# Linux (amd64)
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
sudo install -m 755 cloudflared /usr/local/bin/
cloudflared --version
```

#### 步骤 2：登录并授权域名

```bash
cloudflared tunnel login
# 弹出浏览器 → 选择要授权的 Cloudflare 域名 → 授权完成
# 证书保存在 ~/.cloudflared/cert.pem
```

这一步将你的机器与 Cloudflare 账号关联，获得管理该域名下 Tunnel 的权限。

#### 步骤 3：创建隧道

```bash
cloudflared tunnel create <tunnel-name>
# 输出示例：
# Created tunnel <tunnel-name> with id <tunnel-uuid>
# 凭证文件自动保存到 ~/.cloudflared/<uuid>.json
```

每个 tunnel 有唯一 UUID，凭证 JSON 文件用于后续认证。**不要提交到 git 或公开该文件。**

#### 步骤 4：编写 ingress 配置

创建 `~/.cloudflared/config.yml`：

```yaml
tunnel: <tunnel-uuid>                             # 步骤 3 返回的 UUID
credentials-file: /home/<user>/.cloudflared/<uuid>.json

ingress:
  - hostname: <your-domain>                       # 你的自定义域名
    service: http://localhost:80                  # 本地 nginx 地址
  - service: http_status:404                      # 兜底：其他域名一律 404
```

`ingress` 规则从上到下匹配，最后一条 `http_status:404` 作为默认规则，防止被未授权域名访问。

#### 步骤 5：配置 DNS

在 Cloudflare Dashboard → Zero Trust → Networks → Tunnels 中：
- 点击刚创建的 Tunnel → Configure → Public Hostname
- 添加：`<your-domain>` → Service Type: HTTP → URL: `localhost:80`

或者手动在 DNS 中添加 CNAME 记录：
```
类型: CNAME
名称: stock (或你的子域名)
目标: <tunnel-uuid>.cfargotunnel.com
```

#### 步骤 6：启动隧道

```bash
# 前台运行（调试用，Ctrl+C 停止）
cloudflared tunnel --config ~/.cloudflared/config.yml run

# 后台运行
nohup cloudflared tunnel --config ~/.cloudflared/config.yml run > /tmp/cloudflared.log 2>&1 &

# 安装为系统服务（推荐，开机自启）
sudo cloudflared service install
sudo systemctl enable cloudflared --now
systemctl status cloudflared
```

#### 步骤 7：验证

```bash
# 从外部网络访问
curl https://<your-domain>/api/health
# → {"status":"ok"}

# 查看隧道状态
cloudflared tunnel info <tunnel-name>
```

**完整启动链**（本项目实际运行方式）：

```bash
# 1. 启动 uvicorn（监听 127.0.0.1:8000）
cd ~/stock/stock && source .stock/bin/activate
uvicorn backend.main:app --host 127.0.0.1 --port 8000 &

# 2. 启动 nginx（监听 0.0.0.0:80，反向代理到 :8000）
sudo systemctl start nginx

# 3. 启动 cloudflared（连接隧道，转发域名请求到 nginx :80）
cloudflared tunnel --config ~/.cloudflared/config.yml run
```

数据流：`外部请求 → Cloudflare CDN → cloudflared → nginx:80 → uvicorn:8000`

**常见问题**：

| 问题 | 原因 | 解决 |
|------|------|------|
| `502 Bad Gateway` | cloudflared 连不上本地 nginx | 检查 nginx 是否在 80 端口监听：`ss -tlnp \| grep :80` |
| `ERR Cloudflared Not Connected` | 隧道未运行或已断开 | `systemctl status cloudflared` 检查服务状态 |
| DNS 解析不到 | CNAME 记录未生效 | 检查 Cloudflare DNS 面板确认记录存在，等待 1-5 分钟传播 |
| 访问超时 | 防火墙阻断 cloudflared 出站 | 确保出站 443 (TCP) 到 `*.argotunnel.com` 不受限制 |
