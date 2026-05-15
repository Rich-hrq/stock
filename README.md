# 美股指数波动分析 & 海龟交易法则 RAG 问答

基于《海龟交易法则》的美股指数技术分析网站，支持：

- 四大美股指数（标普500、纳斯达克100、纳斯达克综合、道琼斯）的多时间级别走势图
- 海龟交易法则技术指标：布林带、ATR/N值、唐奇安通道、趋势判断
- 自动生成趋势跟踪投资建议
- 基于原书 PDF 的 RAG 智能问答（LangGraph v3：智能评估 + 选择性扩展 + 多查询融合检索）
- Polymarket 预测市场浏览（独立页面，按事件分组翻页，关键词/活跃日期高亮，概率条可视化）
- The Guardian 新闻资讯（独立页面，爬取最新报道，按分类标签展示，支持原文链接跳转，AI 自动生成当日新闻摘要）
- Guardian 反向代理（通过后端代理访问新闻原文，\<base\> 标签注入 + 域名白名单防滥用）

## 目录结构

```
stock_website/
├── frontend/                  # 前端项目（纯静态 HTML/CSS/JS）
│   ├── index.html            # 主页（指数分析）
│   ├── prediction.html       # 预测市场页
│   ├── news.html             # 新闻资讯页
│   ├── css/
│   │   ├── styles.css        # 主页样式
│   │   ├── prediction.css    # 预测市场页样式
│   │   └── news.css          # 新闻资讯页样式
│   └── js/
│       ├── app.js            # 应用入口，状态管理
│       ├── charts.js         # ECharts K线图 + 布林带 + 唐奇安
│       ├── indicators.js     # 侧边面板：统计、指标、建议
│       ├── chat.js           # RAG 聊天对话框
│       ├── prediction.js     # 预测市场查询与渲染
│       └── news.js           # 新闻抓取与渲染
├── backend/                   # 后端项目（FastAPI）
│   ├── __init__.py           # Python 包标识
│   ├── main.py               # FastAPI 应用入口
│   ├── config.py             # 全局配置（API密钥、指标参数、路径等）
│   ├── schemas.py            # Pydantic 请求/响应模型（接口格式定义）
│   ├── requirements.txt      # Python 依赖
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── index_data.py     # 指数数据 API（/api/indices/*）
│   │   ├── chat.py           # RAG 对话 API（/api/chat）
│   │   ├── prediction.py     # 预测市场 API（/api/predict）
│   │   └── guardian.py       # 新闻爬取 API（/api/guardian_news）
│   │   └── proxy.py           # 反向代理 API（/api/proxy）
│   ├── services/
│   │   ├── __init__.py
│   │   ├── market_data.py    # yfinance 数据获取 + 缓存 + 代理
│   │   ├── indicators.py     # 布林带、ATR、唐奇安通道、趋势判断、投资建议
│   │   ├── polymarket.py     # Polymarket API 数据获取与过滤
│   │   ├── guardian_news.py  # The Guardian 新闻爬取（BeautifulSoup）
│   │   ├── news_summary.py   # AI 新闻摘要（基于新闻标题调用 LLM 生成当日总结）
│   │   ├── proxy.py           # Guardian 反向代理（base 标签注入 + 白名单）
│   │   ├── rag.py            # RAG v1（retrieve → generate）
│   │   ├── rag_v2.py         # RAG v2（rewrite → judge → 条件路由）
│   │   └── rag_v3.py         # RAG v3（evaluate → 选择性扩展 → 多查询融合）
│   └── knowledge/
│       ├── ingest.py         # PDF → 切片 → 向量化 → ChromaDB（一次性脚本）
│       ├── test_rag.py       # v1/v2/v3 对比测试脚本
│       └── chroma_db/        # ChromaDB 持久化向量库（.gitignore）
├── README.md                 # 项目说明
├── guideline.md              # 代码知识讲解 + 数据流 pipeline
└── DEBUG.md                  # 踩坑记录
```

## 环境依赖

- Python 3.12+（使用项目虚拟环境 `.stock/`）
- 主要依赖见 `backend/requirements.txt`

核心依赖用途：

| 包 | 用途 |
|---|---|
| fastapi + uvicorn | Web 框架 + ASGI 服务器 |
| yfinance | 美股指数 OHLCV 数据获取 |
| pandas | 数据处理 |
| langgraph | RAG 流水线编排 |
| langchain-text-splitters | 文本分块（RecursiveCharacterTextSplitter） |
| langchain-anthropic | LLM 调用（支持 Claude / DeepSeek 等 Anthropic 兼容 API） |
| chromadb | 向量数据库，存储知识库嵌入 |
| sentence-transformers | 本地文本嵌入模型 |
| PyMuPDF | PDF 文本提取 |
| anthropic | Anthropic API 客户端 |

## 使用方法

### 1. 激活虚拟环境

```bash
source .stock/bin/activate
```

### 2. 安装依赖

```bash
pip install -r backend/requirements.txt
```

### 3. 设置 API Key

```bash
set -x ANTHROPIC_AUTH_TOKEN sk-ant-xxx   # fish shell
# 也支持 ANTHROPIC_API_KEY 环境变量名
```
> 聊天功能支持 Anthropic 官方 API 及兼容服务（如 DeepSeek），详见「服务管理」章节。

### 4. 构建知识库（首次运行，一次性）

```bash
python backend/knowledge/ingest.py
```

> 这将读取 `../海龟交易法则.pdf`（约256页），切片后向量化存入 ChromaDB。
> 首次运行约需 2-3 分钟（取决于机器速度），后续无需重复。

### 5. 启动服务

```bash
# 完整启动命令（含代理 + LLM API），从 stock_website 目录执行
all_proxy=http://127.0.0.1:7897 uvicorn backend.main:app --reload --port 8000
```

> 或参考下方「服务管理」章节进行启动、停止、重启。

### 6. 访问

- 主页（指数分析）：http://localhost:8000
- 预测市场页：http://localhost:8000/prediction.html
- 新闻资讯页：http://localhost:8000/news.html
- API 文档（Swagger）：http://localhost:8000/docs

---

## 服务管理

### 环境变量

| 变量 | 必需 | 说明 |
|------|------|------|
| `all_proxy` | 建议 | HTTP 代理，国内环境访问 Yahoo Finance / HuggingFace 需要 |
| `ANTHROPIC_AUTH_TOKEN` | 聊天功能必需 | LLM API Key（也支持 `ANTHROPIC_API_KEY`） |
| `ANTHROPIC_BASE_URL` | 可选 | 自定义 API 端点（如使用 DeepSeek 等兼容服务） |
| `ANTHROPIC_MODEL` | 可选 | 模型名称，默认 `claude-sonnet-4-6` |

### 启动服务

```bash
# 从 stock_website 目录执行，不含聊天功能（仅指数分析）：
all_proxy=http://127.0.0.1:7897 /path/to/.stock/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 &

# 含聊天功能（需设置 LLM 环境变量）：
env all_proxy=http://127.0.0.1:7897 \
    ANTHROPIC_AUTH_TOKEN=<your-api-key> \
    ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic \
    ANTHROPIC_MODEL='deepseek-v4-pro[1m]' \
    /path/to/.stock/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
```

**参数说明：**
- `--host 0.0.0.0`：允许局域网内其他设备访问（仅本机使用可设为 `127.0.0.1`）
- `--port 8000`：监听端口
- `--reload`：开发模式，代码变更时自动重启（生产环境不要用）
- 末尾 `&`：后台运行

### 检查运行状态

```bash
# 方法1：健康检查接口
curl http://localhost:8000/api/health
# 返回 {"status":"ok"} 即正常运行

# 方法2：检查端口占用
lsof -i:8000
```

### 停止服务

```bash
# 方法1：查找并终止 uvicorn 进程
pkill -f "uvicorn backend.main"

# 方法2：通过端口终止
lsof -ti:8000 | xargs kill

# 方法3：强制终止
lsof -ti:8000 | xargs kill -9
```

### 重启服务

```bash
lsof -ti:8000 | xargs kill 2>/dev/null; sleep 1
# 再执行「启动服务」命令
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/indices` | 返回可用指数列表 |
| GET | `/api/indices/{symbol}/analysis?start_date=...&end_date=...` | 完整技术分析（OHLCV + 指标 + 建议） |
| POST | `/api/chat` | RAG 对话（body: `{message, history?}`） |
| POST | `/api/predict` | Polymarket 预测数据（body: `{keywords, limit?, threshold?}`） |
| POST | `/api/guardian_news` | The Guardian 新闻爬取（无需参数） |
| POST | `/api/news/summary` | AI 新闻摘要（body: `{headlines: [{title, link}, ...]}`） |
| GET | `/api/proxy?url=...` | Guardian 反向代理（仅限 www.theguardian.com） |
| GET | `/api/health` | 健康检查 |

## 技术架构

```
浏览器 ──→ FastAPI ──→ /api/indices/  ──→ yfinance（Yahoo Finance）
    │                      │                    │
    │                      ├──→ /api/chat ──→ LangGraph ──→ ChromaDB ──→ LLM
    │                      │                    │
    │                      ├──→ /api/predict ──→ Polymarket API
    │                      ├──→ /api/guardian_news ──→ The Guardian
    │                      ├──→ /api/news/summary ──→ news_summary.py ──→ LLM（生成当日摘要）
    │                      ├──→ /api/proxy ──→ Guardian 反向代理
    │                      │
    └──← 前端静态文件（HTML/CSS/JS）              ├─ v1: retrieve → generate
                                               ├─ v2: rewrite → retrieve → judge → 条件路由
                                               └─ v3: evaluate → 选择性扩展 → 多查询融合 → generate
```

## 海龟交易法则指标说明

### 技术指标参数

| 指标 | 参数 | 说明 |
|------|------|------|
| 布林带 | 20周期, 2σ | 中轨=MA20，上下轨=±2个标准差，衡量波动范围 |
| ATR / N值 | 20周期 | 平均真实波幅，海龟用N值决定头寸规模（1N=账户的1%风险） |
| 唐奇安通道 系统1 | 20日高点/10日低点 | 短期突破信号 |
| 唐奇安通道 系统2 | 55日高点/20日低点 | 长期突破信号 |

### 统计指标计算标准

所有统计指标基于所选时间范围内的 OHLC 完整四价计算，采用 yfinance **日线数据**（跨日查询）或**小时线数据**（同日查询）。

> 数据粒度自动选择规则：同日查询（起止日期相同）使用 `1h`，跨日查询使用 `1d`。日线数据与 Yahoo Finance 网页端 OHLC 数值完全一致。

| 指标 | 公式 | 说明 |
|------|------|------|
| 起始价 | `df["open"].iloc[0]` | 所选区间首根 K 线的开盘价 |
| 当前价 | `df["close"].iloc[-1]` | 所选区间末根 K 线的收盘价 |
| 最高价 | `df["high"].max()` | 区间内真实最高成交价 |
| 最低价 | `df["low"].min()` | 区间内真实最低成交价 |
| **区间涨跌 (O→C)** | `(当前价 − 起始价) / 起始价 × 100%` | 从区间开盘到收盘的涨跌幅，反映所选周期内的价格变化 |
| **日涨跌 (P→C)** | `(当前价 − 前日收盘) / 前日收盘 × 100%` | 从前一交易日收盘到当前价的涨跌幅，与 Yahoo Finance「% Change」对齐 |
| 前日收盘 | 区间起始日前一交易日的收盘价 | 通过额外获取日线数据得到，作为日涨跌的基准 |
| 区间振幅 | `(最高价 − 最低价) / 起始价 × 100%` | 区间内价格波动的最大幅度 |
| 当前趋势 | 唐奇安通道突破判断 | 价格≥20日高点→上升趋势；≤20日低点→下降趋势；否则盘整 |

**颜色规则**：
- 涨跌幅以 `+` 开头（正收益）→ 绿色 (`#4caf50`)；否则 → 红色 (`#ef5350`)
- K 线：`close >= open` → 绿；`close < open` → 红（国际通用惯例）

### 蓝绿涨跌对比

| | 区间涨跌 (O→C) | 日涨跌 (P→C) |
|------|-----------|----------|
| 基准 | 区间首根 K 线开盘价 | 前一交易日收盘价 |
| 适用场景 | 任意时间范围，语义统一 | 与 Yahoo Finance 对标 |
| 示例（^NDX 5/14） | (29580.30 − 29372.65) / 29372.65 = **+0.71%** | (29580.30 − 29366.94) / 29366.94 = **+0.73%** |
