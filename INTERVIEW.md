# 面试准备：RAG (LangGraph) + 前后端分离网站开发

本文档基于「美股指数波动分析 & 海龟交易法则 RAG 问答」项目的实际构建经验，从面试角度深入讲解技术细节、设计决策和常见追问。

---

## 第一部分：RAG — 检索增强生成 (LangGraph + ChromaDB)

### 1.1 什么是 RAG？为什么要用它？

**核心概念**：RAG (Retrieval-Augmented Generation) = 检索 + 生成。在 LLM 生成回答之前，先从外部知识库中检索相关文档，将检索结果作为上下文注入 Prompt，让 LLM 基于这些上下文生成回答。

**我们项目的场景**：用户询问海龟交易法则相关问题。如果我们直接让 LLM 回答，它会依靠训练数据中的记忆，可能不准确、过时或产生幻觉。RAG 的做法是：先从《海龟交易法则》PDF 原书中检索相关段落，然后把"书中原文 + 用户问题"一起发给 LLM，LLM 严格基于原文回答。

**RAG 解决的核心问题**：
- **知识时效性**：LLM 训练截止日期后的新内容无法覆盖 → RAG 使用最新文档
- **幻觉 (Hallucination)**：LLM 可能编造事实 → RAG 用原文约束输出
- **领域专业性**：通用 LLM 对特定领域理解不深 → RAG 以专业文档为知识基底
- **可溯源**：回答可以标注"出自哪一页"，而不是黑盒输出

### 1.2 我们的 RAG 流水线全景

```
                       ┌─── 离线阶段（一次性）──┐
                       │                         │
  海龟交易法则.pdf ──→ PyMuPDF 提取文本 ──→ RecursiveCharacterTextSplitter 分块
      256页                                      │
                                             427个文本块
                                                 │
                                    SentenceTransformer 嵌入
                                    (paraphrase-multilingual-MiniLM-L12-v2)
                                                 │
                                          ChromaDB 持久化存储
                                                 │
                       └─────────────────────────┘

                       ┌─── 在线阶段（每次请求）──┐
                       │                          │
  用户提问 ──→ SentenceTransformer 编码为向量 ──→ ChromaDB 相似度搜索 (top-4)
                                                          │
                                                    4个最相关文本块
                                                          │
                              ┌───────────────────────────┘
                              │
                  组装 Prompt（指令 + 原文 + 历史 + 问题）
                              │
                   LangGraph 状态图:
                     Node 1: retrieve ──→ Node 2: generate
                              │
                        Claude/DeepSeek 生成回答
                              │
                   返回 { answer, sources[{page, text}] }
```

### 1.3 知识库构建详解

#### 1.3.1 PDF 文本提取 — PyMuPDF (fitz)

```python
import fitz  # PyMuPDF
doc = fitz.open("海龟交易法则.pdf")
for page in doc:
    text = page.get_text()
```

**为什么选 PyMuPDF？**
- 中文提取准确率高，不会出现乱码
- 速度快：256 页 PDF 秒级完成
- 相比 pdfplumber 更轻量，相比 PyPDF2 中文支持更好

**实际收获**：255 页有效文本（含封面和目录，保留了页码元数据）

#### 1.3.2 文本分块策略 — 面试必考重点

这是我们项目中最值得深入讨论的工程决策之一。

**我们使用的方案**：
```python
RecursiveCharacterTextSplitter(
    chunk_size=500,        # 每块最多 500 字符
    chunk_overlap=50,      # 相邻块重叠 50 字符
    separators=["\n\n", "\n", "。", "！", "？", "；", ".", " ", ""]
)
```

**分块大小 (chunk_size) 的影响——面试高频问题**：

| 分块大小 | 优点 | 缺点 |
|---------|------|------|
| 太小 (100-200) | 检索精度高，能精确定位到具体句子 | 丢失上下文，LLM 只能看到碎片，回答可能不完整 |
| 适中 (500-1000) | 保留完整段落语义，兼顾精度和上下文 | 可能包含一些无关句子 |
| 太大 (2000+) | 上下文完整 | 检索信号稀释，可能把不相关的内容也带入 Prompt，浪费 token |

**我们选择 500 的原因**：
1. 中文约 500 字符 ≈ 一段到两段，是完整的语义单元
2. 海龟交易法则作为专业书籍，一个概念通常在一个段落内说清
3. 配合 `separators=["\n\n", "\n", "。", ...]`，优先按自然段落分割
4. 427 个文本块对 256 页的书来说粒度合适

**重叠 (overlap=50) 的作用**：
- 防止关键信息恰好卡在两个 chunk 的边界上被切断
- 50 字符重叠 ≈ 一句话，保证边界处的语义连续性
- 代价很小：只增加约 10% 的存储和检索开销

**RecursiveCharacterTextSplitter 的工作原理**：
```
1. 尝试用 "\n\n"（空行/段落分隔）切分
2. 如果某段仍然超过 chunk_size，再用 "\n"（行分隔）切分
3. 如果某行仍然过长，再用 "。"（句号）切分
4. 依此类推...
5. 如果单个句子超过 chunk_size，强制按字符切断
```
这是一种"从粗到细"的递归策略，优先保留自然文档结构。

**面试可能被追问**：
> **Q: 为什么不直接用固定长度切分？**
> A: 固定长度（如每 500 字符一刀）会在句子中间切断，破坏语义。RecursiveCharacterTextSplitter 尝试在自然分隔符处切割，保持语义完整性。

> **Q: 怎么确定最优的 chunk_size？**
> A: 没有万能值。经验法则：chunk_size 应该能容纳一个完整的"知识点"。对我的项目来说，海龟交易法则的一个交易规则通常 2-3 段说清楚，500 字符刚好。更好的方式是用评估集测试不同 chunk_size 的检索效果。

#### 1.3.3 嵌入模型选择

```python
# 我们使用的模型
model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
# 输出：384 维向量
```

**关键属性**：
- **多语言**：`paraphrase-multilingual` 前缀表示支持 50+ 语言，中文表现良好
- **MiniLM**：轻量架构，推理速度快，CPU 上也能跑
- **L12**：12 层 Transformer，在速度和质量间平衡
- **384 维**：向量维度适中，在精度和存储间平衡

**为什么不直接用 OpenAI Embeddings？**
- 省钱：本地运行零 API 费用
- 隐私：文档不会离开本地
- 不过第一次下载 ~400MB 模型需要网络（而且是 HuggingFace，需要代理）

**面试可能被追问**：
> **Q: 向量维度 (384) 的大小有什么影响？**
> A: 更高维度 (768/1024) 表达能力更强但存储和检索更慢。384 维对中等规模知识库足够。我们 427 个文本块 × 384 维的存储量非常小，检索毫秒级。

#### 1.3.4 ChromaDB 向量数据库

```python
# 存储
client = chromadb.PersistentClient(path="./chroma_db")
collection = client.create_collection(name="turtle_trading")
collection.add(
    ids=["chunk_0", ...],
    documents=["文本块内容...", ...],
    metadatas=[{"page": 1}, ...],
    embeddings=[[0.1, 0.2, ...], ...]
)

# 检索
results = collection.query(
    query_embeddings=[[0.12, -0.34, ...]],
    n_results=4
)
```

**为什么选 ChromaDB？**
- **零运维**：一个文件目录就是整个数据库，不需要单独启动服务
- **Python 原生**：API 简洁，和 LangChain/LangGraph 生态天然集成
- **持久化**：重启不丢数据，知识库只需构建一次
- **对小规模场景足够**：数百到数千个文档，ChromaDB 绰绰有余

**注意重点**：
- 默认使用余弦相似度 (cosine similarity) 做向量检索
- 支持 metadata 过滤（我们用它存页码，可以在回答中引用具体位置）
- 分批次存入（每批 100 条），避免一次性加载所有嵌入造成 OOM

**面试可能被追问**：
> **Q: 什么时候 ChromaDB 不够用，需要换别的向量数据库？**
> A: 当文档量达到百万级以上，或者需要分布式部署、高并发检索时。此时可考虑 Milvus（性能更强）、Weaviate（自带混合搜索）、Pinecone（全托管）等。但对于大多数原型和中小项目，ChromaDB 足够。

> **Q: 为什么不直接把整个 PDF 的内容作为 Prompt context？**
> A: 两个原因：(1) LLM 的 context window 有限——256 页书远超 token 限制；(2) Prompt 中无关内容越多，LLM 越容易被干扰（"lost in the middle" 问题），回答质量反而下降。检索的作用就是"大海捞针"，从全书找到最相关的 4 个段落。

### 1.4 LangGraph 状态图编排

这是我们的 RAG 流水线的"大脑"。LangGraph 提供了比 LangChain 更灵活的图编排能力。

#### 1.4.1 状态定义

```python
class RAGState(TypedDict):
    question: str          # 用户问题
    history: list[dict]    # [{role, content}] 多轮对话历史
    context: list[str]     # 检索节点填充：最相关的文本块
    sources: list[dict]    # [{page, text}] 来源元数据
    answer: str            # 生成节点填充：最终回答
```

#### 1.4.2 图的构建——两节点流水线

```python
graph = StateGraph(RAGState)

graph.add_node("retrieve", retrieve_node)   # 节点1：检索
graph.add_node("generate", generate_node)   # 节点2：生成

graph.set_entry_point("retrieve")           # 入口 = 检索
graph.add_edge("retrieve", "generate")      # 检索 → 生成
graph.add_edge("generate", END)             # 生成 → 结束

rag_app = graph.compile()
```

#### 1.4.3 检索节点 (retrieve_node)

```python
def retrieve_node(state: RAGState) -> dict:
    # 1. 将用户问题编码为向量
    query_embedding = embed_model.encode(state["question"])
    # 2. 在 ChromaDB 中搜索 top-4 最相关的文本块
    results = collection.query(query_embeddings=..., n_results=4)
    # 3. 返回上下文和来源
    return {"context": [...], "sources": [{"page": 238, "text": "..."}]}
```

**为什么是 top-4？**
- 太少 (1-2)：可能遗漏关键信息
- 太多 (8-10)：上下文过长，token 消耗大，且噪声增多
- top-4 在质量和效率间有良好的平衡

#### 1.4.4 生成节点 (generate_node)

```python
def generate_node(state: RAGState) -> dict:
    prompt = """你是海龟交易法则的专家助手。
    规则：
    1. 严格基于提供的原文内容回答
    2. 如果原文中没有足够信息，告知用户"书中未提及"
    3. 引用原文页码
    4. 使用中文

    原文内容：
    ---
    {context}
    ---

    用户问题：{question}
    """
    response = llm.invoke(prompt)
    return {"answer": response_text}
```

**这个 Prompt 设计的要点**：
1. **"严格基于原文"** — 这是 RAG 最关键的约束，防止 LLM 脱离上下文编造
2. **"书中未提及"** — 设定安全边界，避免强行回答
3. **"引用页码"** — 让回答可验证、可溯源
4. **"使用中文"** — 适配用户语言

#### 1.4.5 为什么用 LangGraph 而不是直接串行调用？

**面试高频追问**——这个问题能看出你是否真的理解了工具的价值。

| 方案 | 当前适用 | 扩展时的问题 |
|------|---------|------------|
| 直接串行调用 | ✅ 简单检索→生成场景 | 逻辑复杂时变成面条代码 |
| LangChain Chain | ✅ 线性流程 | 条件分支、循环、并行很困难 |
| **LangGraph StateGraph** | ✅ 当前也适用 | 天然支持复杂流程扩展 |

**LangGraph 的真正优势在扩展时**：

```python
# 一个更复杂的 RAG 流程（现在就可以加）：
# 入口 → 问题改写(rewrite) → 检索 → 判断相关性 →
#   ┌→ 高度相关 → 直接生成答案 → END
#   └→ 低相关 → 改写问题 → 检索 → 生成(带不确定性说明) → END

graph.add_node("rewrite", rewrite_question)
graph.add_node("retrieve", retrieve)
graph.add_node("judge", judge_relevance)
graph.add_node("generate", generate)
graph.add_node("generate_uncertain", generate_with_disclaimer)

graph.add_conditional_edges("judge", decide_path, {
    "relevant": "generate",
    "not_relevant": "rewrite",  # 回环！重新改写问题
})
```

这种条件分支 + 循环在传统串行代码中很难优雅表达，LangGraph 原生支持。

### 1.5 完整 RAG 面试追问清单

#### Q1: 如何评估 RAG 系统的质量？
**A**: 三个维度：
- **检索质量** (Recall@K)：检索到的文档是否真的和问题相关？用标注数据集（问题→正确答案段落）测试
- **生成质量** (Faithfulness)：生成的回答是否忠实于检索到的上下文？是否产生了幻觉？
- **端到端质量**：用户是否得到满意答案？可以用 LLM-as-judge 自动评估
- 我们项目的实际做法：手动测试 5-10 个典型问题，逐条检查引用页码和回答准确性

#### Q2: 检索不到相关内容怎么办？
**A**: 多种策略：
- 问题改写 (Query Rewriting)：用 LLM 重新措辞用户的模糊问题
- 混合检索 (Hybrid Search)：向量检索 + BM25 关键词检索，两者互补
- 降低检索阈值：如果 top-4 的相似度都很低（如 < 0.5），说明库中没有相关内容，应明确告知用户

#### Q3: 为什么要用嵌入模型做语义检索，而不是直接用关键词匹配？
**A**: 关键词匹配只能找到字面相同的词。例如用户问"入市"，书中用的是"入市法则"，关键词可能匹配不上。而嵌入模型能理解"入市"和"入市法则"在语义上的关联性，即使字面不同也能检索到。

#### Q4: RAG 的局限是什么？
**A**: 
- 检索不到 ≠ 书中没有：当前检索可能不是完美的
- Lost in the middle：长 context 中，LLM 倾向于关注开头和结尾，中间部分容易被忽视
- 上下文冲突：检索到的多个片段可能包含矛盾信息
- 对复杂推理支持有限：需要跨多个段落综合推理的问题，RAG 可能力不从心

---

## 第二部分：网站开发 — 前后端分离架构

### 2.1 整体架构

```
┌────────────────────────────────────────────────────┐
│                    浏览器 (Client)                   │
│  ┌──────────────┐  ┌────────────┐  ┌────────────┐  │
│  │  ECharts 图表  │  │  指标面板   │  │  RAG 聊天   │  │
│  └──────┬───────┘  └─────┬──────┘  └─────┬──────┘  │
│         │               │               │          │
│         └───────────────┼───────────────┘          │
│                         │ fetch() 调用 REST API      │
└─────────────────────────┼──────────────────────────┘
                          │ HTTP/JSON
┌─────────────────────────┼──────────────────────────┐
│              FastAPI (后端服务器)                     │
│                         │                           │
│  ┌──────────────────────┴──────────────────────┐   │
│  │           CORS Middleware (跨域)              │   │
│  ├──────────────┬──────────────────┬───────────┤   │
│  │ /api/indices │   /api/chat      │  / (静态)  │   │
│  │ Router       │   Router          │  StaticFiles│   │
│  ├──────┬───────┼──────┬───────────┤   (前端页面) │   │
│  │market│indic..│      │ LangGraph │              │   │
│  │_data │ors    │      │ + Claude  │              │   │
│  │(yfi..│(BB/ATR│      │ + ChromaDB│              │   │
│  │nance)│ /DC)  │      │            │              │   │
│  └──────┴───────┘      └────────────┘              │   │
└────────────────────────────────────────────────────┘
```

**前后端分离的关键特征**：
- 后端只返回 JSON 数据，不渲染 HTML
- 前端是独立的静态文件 (HTML + CSS + JS)，通过 API 获取数据
- 前端在任何地方都可以部署：同一服务器、CDN、甚至本地文件
- 前后端通过明确的 API 契约通信

### 2.2 后端：FastAPI 设计详解

#### 2.2.1 为什么是 FastAPI？

| 框架 | async | 自动文档 | 类型校验 | 学习曲线 | 适合场景 |
|------|-------|---------|---------|---------|---------|
| **FastAPI** | ✅ 原生 | ✅ Swagger | ✅ Pydantic | 中 | API 服务、AI/ML 项目 |
| Django | ⚠️ 有限 | 需插件 | ⚠️ 部分 | 高 | 传统网站、CMS、后台管理 |
| Flask | ❌ | 需插件 | ❌ | 低 | 简单 API、微服务 |

**我们这个项目的契合点**：
- LangGraph 是 async 的，FastAPI 原生 async 无阻抗
- Pydantic 的类型校验天然适合 API 参数校验
- Swagger 自动生成接口文档，调试方便

#### 2.2.2 目录分层

```
backend/
├── main.py          # 入口：创建 FastAPI app，挂载中间件和路由
├── config.py        # 配置：所有环境变量、常量
├── routers/         # 路由层：处理 HTTP 请求/响应，参数校验
│   ├── index_data.py
│   └── chat.py
├── services/        # 业务层：核心逻辑，与 HTTP 无关
│   ├── market_data.py  # yfinance 数据获取
│   ├── indicators.py   # 技术指标计算
│   └── rag.py          # LangGraph RAG 流水线
└── knowledge/
    └── ingest.py       # 知识库接入
```

**分层的好处（面试要点）**：

- **Router 层**只管 HTTP 相关的事情：接收请求、参数校验、返回响应
- **Service 层**是纯 Python 逻辑，不依赖 HTTP，可以独立测试和复用
- 如果你想换 Web 框架（如从 FastAPI 换到 Flask），只需要改 Router 层

#### 2.2.3 相对导入与包管理

```python
# main.py
from .config import STATIC_DIR          # 相比 from config import ...
from .routers import index_data, chat    # 包内相对导入

# routers/index_data.py
from ..services.market_data import ...   # 向上一级再进入 services
from ..config import US_INDEXES
```

**为什么用相对导入？** 当模块在包内时，相对导入确保从哪里启动都能找到正确的模块。我们实际踩过这个坑——用 `from config import ...` 时 `uvicorn backend.main:app` 找不到 config。

#### 2.2.4 CORS — 跨域资源共享

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],    # 允许所有来源
    allow_methods=["*"],    # 允许所有 HTTP 方法
    allow_headers=["*"],
)
```

**为什么需要 CORS？** 浏览器同源策略默认禁止跨域请求。前后端分离部署时，前端（如 `localhost:3000`）和后端（`localhost:8000`）是不同的"源"。`allow_origins=["*"]` 在生产环境应替换为具体域名。

**面试可能被追问**：
> **Q: allow_origins=["*"] 有什么安全风险？**
> A: 允许任何网站向你的 API 发请求。恶意网站可以在用户不知情的情况下调用你的 API（CSRF）。生产环境应限制为前端部署的具体域名。

#### 2.2.5 async def 和同步阻塞

```python
@router.get("/{symbol}/analysis")
async def get_index_analysis(...):  # async 函数
    df = fetch_index_data(...)       # 这是一个同步调用！
```

**这里有个真实问题**：`yfinance.Ticker.history()` 是同步的 I/O 操作。在 async 函数中调用同步阻塞函数会阻塞整个 event loop。解决方法：
- 用 `run_in_executor` 将同步操作放到线程池
- 或接受当前限制（因为这个接口并发量不高）

**面试时可以说**：实际项目中发现 yfinance 的调用耗时主要在网络上（等待 Yahoo 响应），在 async 端点中调用它虽然不是最优实践，但在低并发场景下影响不大。如果要优化，可以用 `asyncio.to_thread()` 包装。

### 2.3 API 设计

#### 2.3.1 RESTful 风格

| 方法 | 路径 | 含义 |
|------|------|------|
| GET | `/api/indices` | 获取指数列表（资源列表） |
| GET | `/api/indices/{symbol}/analysis` | 获取单个指数的分析（资源详情） |
| POST | `/api/chat` | 创建一次对话（非幂等操作） |
| GET | `/api/health` | 健康检查（运维接口） |

**设计要点**：
- 资源名用名词复数 (`indices` 而非 `index`)
- 用路径参数表示资源标识 (`{symbol}`)
- 查询参数用 query string (`?start_date=...`)
- 状态变更操作用 POST

#### 2.3.2 Pydantic 请求/响应模型

```python
class ChatRequest(BaseModel):
    message: str
    history: list[dict] | None = None

class ChatResponse(BaseModel):
    answer: str
    sources: list[dict]
```

**Pydantic 的价值**：
- 自动校验请求格式：`message` 必须存在且为字符串
- 自动生成 OpenAPI 文档：Swagger UI 可以直接看到请求/响应格式
- 类型安全：IDE 自动补全

**我们碰到的一个坑**：DeepSeek 的响应格式是 `list[dict]`（content blocks），但 `ChatResponse.answer` 期望 `str`，导致 Pydantic 校验失败。这种跨 API 兼容性问题在实际开发中很常见，解决方案是加适配层。

### 2.4 数据层

#### 2.4.1 外部 API 调用 — yfinance

```python
def fetch_index_data(symbol, start_date, end_date, interval=None):
    if interval is None:
        interval = auto_interval(start_date, end_date)  # 自动选择粒度
    raw = yf.Ticker(symbol).history(start=start, end=end, interval=interval)
    raw.columns = [c.lower() for c in raw.columns]  # 统一列名
    return raw
```

**国内网络问题**：Yahoo Finance 在国内无法直连，需要设置 `all_proxy`。这是"基础设施即代码"的一个例子——环境变量管理部署差异，代码本身不需要改。

#### 2.4.2 缓存

我们使用 `functools.lru_cache` 对指数名称查询做缓存。对于 yfinance 的数据调用没有缓存——因为用户每次选择的日期范围都可能不同。如果要加缓存，可以考虑：

- Redis 做服务级缓存（适合分布式部署）
- `cachetools.TTLCache` 做时间窗口缓存（同一个时间段内相同请求不重复调 API）

### 2.5 前端架构（前后端分离的前端）

#### 2.5.1 SPA 单页应用 — 无框架方案

我们选择**不使用前端框架**（React/Vue），而是原生 JS + ECharts。这是有意为之的设计决策：

**什么时候不用框架是对的？**
- 只有 1 个主页面，6 个 JS 文件，状态管理简单
- 团队或项目规模小，引入框架的成本 > 收益
- 学习目的：先理解原生 API 再学框架，地基更牢

**代码组织方式**：每个 JS 文件是一个 IIFE (Immediately Invoked Function Expression) 模块，通过 `window` 对象暴露公共函数：

```javascript
// charts.js
(function () {
    function renderChart(data) { /* ... */ }
    window.renderChart = renderChart;  // 暴露给其他模块
})();

// app.js
(function () {
    // 可以调用 window.renderChart(data)
})();
```

**IIFE 的作用**：创建私有作用域，避免全局变量污染。`"use strict"` 启用严格模式。

#### 2.5.2 API 通信

```javascript
// 前端通过 fetch() 调用后端 API
const res = await fetch("/api/indices/^GSPC/analysis?start_date=...&end_date=...");
const data = await res.json();
// data = { symbol, name, data[], stats, advice }
```

- 所有 API 调用通过 `fetch()` 进行（浏览器原生，不需要 axios）
- 响应数据是 JSON，前端负责渲染

**错误处理模式**：
```javascript
try {
    const res = await fetch(url);
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "加载失败");
    }
    // 使用 data...
} catch (e) {
    showError(e.message);  // 用户友好的错误提示
}
```

#### 2.5.3 ECharts 图表渲染

```javascript
option = {
    series: [
        // 绘制顺序决定层级：先画的在底层
        { name: "布林下轨", type: "line", areaStyle: {...} },   // 最底层：带面积
        { name: "布林中轨", type: "line" },
        { name: "布林上轨", type: "line" },
        { name: "唐奇安上轨", type: "line" },
        { name: "唐奇安下轨", type: "line" },
        { name: "K线", type: "candlestick", data: [[open,close,low,high],...] }, // 最上层
        { name: "成交量", type: "bar" },
    ]
};
chart.setOption(option);
```

**关键点**：
- ECharts `candlestick` 类型直接接受 `[open, close, low, high]` 格式
- 通过 `xAxisIndex` / `yAxisIndex` 实现同一图表的多坐标系（K线用主坐标，成交量用次坐标）
- `tooltip.formatter` 自定义提示框内容，显示 OHLC + 布林带 + 唐奇安通道数据

#### 2.5.4 状态管理（无框架方案）

```javascript
const state = {
    indices: [],
    currentSymbol: null,
    currentDays: 180,
    isSloading: false,
};
```

- 单个状态对象保存所有应用状态
- 通过 `loadData()` → `renderChart()` → `renderIndicators()` 单向数据流
- 没有响应式绑定，手动从状态对象读取并更新 DOM

### 2.6 后端面试追问

#### Q1: 如何处理 yfinance API 的限流和失败？
**A**: 我们目前用 `try/except` 捕获异常并返回用户友好的错误信息。更完善的方案：
- 指数退避重试 (exponential backoff)
- 多级缓存减少请求频率
- 降级策略：如果实时数据获取失败，返回最近一次缓存的数据
- 加入请求限流中间件保护后端（`slowapi` 库）

#### Q2: 你的 API 有没有限流保护？
**A**: 当前是原型阶段，没有。如果要加，可以使用 `slowapi` (基于 `limits`) 或 FastAPI 的 `Middleware` 对每个 IP 做速率限制。yfinance 侧的限流由 Yahoo 控制，我们无法干预。

#### Q3: 静态文件挂在 API 前面会导致什么问题？
**A**: `app.mount("/", StaticFiles(...))` 会捕获所有未被前面路由处理的请求。这意味着：
- `/api/health` 能正常工作（先注册的路由先生效）
- 但如果 API 路径写错（如 `/api/indicess`），会被 StaticFiles 捕获并返回 404，而不是"API 路径不存在"的提示。解决方案：给 StaticFiles 挂一个不常用的前缀如 `/app/`。

### 2.7 系统扩展方向

| 方向 | 具体做法 |
|------|---------|
| 数据库 | SQLite/PostgreSQL 存储历史查询、用户配置 |
| 用户系统 | JWT 认证 + 用户收藏的指数组合 |
| 实时推送 | WebSocket 推送实时指数数据 |
| 前端升级 | React + TypeScript，ECharts 通过 echarts-for-react 集成 |
| RAG 增强 | 混合检索 (BM25 + 向量)、Query Rewriting、结果重排序 |
| 部署 | Docker 容器化 + Nginx 反向代理 + HTTPS |

---

## 附录：面试话术参考

### "请简单介绍一下这个项目"

"我做了一个美股指数分析网站，后端用 FastAPI，前端是原生 JS + ECharts。核心功能有两个：

一是展示美股四大指数的走势图和技术指标——包括布林带、ATR/N值、唐奇安通道，这些都是来自《海龟交易法则》原书的策略。后端通过 yfinance 获取数据，计算指标，生成投资建议。

二是做了一个基于 RAG 的智能问答，用 LangGraph 编排流水线。我把《海龟交易法则》256 页的 PDF 用 PyMuPDF 提取文本，切分成 427 个语义块，用 sentence-transformers 做嵌入，存入 ChromaDB。用户提问时，系统先从向量库检索最相关的原文段落，再用 LLM 基于原文生成答案，严格限制不编造，并且标注出处页码。

整个项目从需求分析、架构设计、到编码实现、测试验证都是自己完成的。比较有意思的一个坑是 DeepSeek API 的响应格式和标准 Anthropic 不一致，需要做适配层解析 content blocks。"

### "项目里最大的技术挑战是什么？"

"我觉得是 RAG 系统的分块策略选择。chunk_size 直接影响检索质量——太小丢失上下文，太大稀释信号。对于一本 256 页的专业书，500 字符的 chunk_size 配合 50 字符 overlap 是一个平衡点。我用了 RecursiveCharacterTextSplitter 而不是简单按字符截断，因为它从段落 → 行 → 句子 → 字符逐级尝试切割，优先保持语义完整性。这个选择是我在理解了几种分块方案后才确定的。"

---

> 本文档会随项目迭代持续更新。每次面试后若有新的高频问题或更深的理解，应该补充进来。
