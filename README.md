# 美股指数波动分析 & 海龟交易法则 RAG 问答

基于《海龟交易法则》的美股指数技术分析网站，支持：

- 四大美股指数（标普500、纳斯达克100、纳斯达克综合、道琼斯）的多时间级别走势图
- 海龟交易法则技术指标：布林带、ATR/N值、唐奇安通道、趋势判断
- 自动生成趋势跟踪投资建议
- 基于原书 PDF 的 RAG 智能问答（LangGraph + ChromaDB + Claude）

## 目录结构

```
stock_website/
├── backend/
│   ├── main.py              # FastAPI 应用入口
│   ├── config.py            # 全局配置（API密钥、指标参数等）
│   ├── requirements.txt     # Python 依赖
│   ├── routers/
│   │   ├── index_data.py    # 指数数据 API（/api/indices/*）
│   │   └── chat.py          # RAG 对话 API（/api/chat）
│   ├── services/
│   │   ├── market_data.py   # yfinance 数据获取 + 缓存 + 代理
│   │   ├── indicators.py    # 布林带、ATR、唐奇安通道、趋势判断、投资建议
│   │   └── rag.py           # LangGraph RAG 流水线（检索 + 生成）
│   ├── knowledge/
│   │   ├── ingest.py        # PDF → 切片 → 向量化 → ChromaDB（一次性脚本）
│   │   └── chroma_db/       # ChromaDB 持久化向量库（.gitignore）
│   └── static/              # 前端静态文件
│       ├── index.html
│       ├── css/styles.css
│       └── js/
│           ├── app.js       # 应用入口，状态管理
│           ├── charts.js    # ECharts K线图 + 布林带 + 唐奇安
│           ├── indicators.js # 侧边面板：统计、指标、建议
│           └── chat.js      # RAG 聊天对话框
├── README.md                # 项目说明
├── guideline.md             # 代码知识讲解 + 数据流 pipeline
└── DEBUG.md                 # 踩坑记录
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
| langchain-anthropic | Claude LLM 调用 |
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
set -x ANTHROPIC_API_KEY sk-ant-xxx   # fish shell
# 或 export ANTHROPIC_API_KEY=sk-ant-xxx  # bash
```

### 4. 构建知识库（首次运行，一次性）

```bash
python backend/knowledge/ingest.py
```

> 这将读取 `../海龟交易法则.pdf`（约256页），切片后向量化存入 ChromaDB。
> 首次运行约需 2-3 分钟（取决于机器速度），后续无需重复。

### 5. 启动服务

```bash
uvicorn backend.main:app --reload --port 8000
```

### 6. 访问

- 前端页面：http://localhost:8000
- API 文档（Swagger）：http://localhost:8000/docs

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/indices` | 返回可用指数列表 |
| GET | `/api/indices/{symbol}/analysis?start_date=...&end_date=...` | 完整技术分析（OHLCV + 指标 + 建议） |
| POST | `/api/chat` | RAG 对话（body: `{message, history?}`） |
| GET | `/api/health` | 健康检查 |

## 技术架构

```
浏览器 ──→ FastAPI ──→ /api/indices/  ──→ yfinance（Yahoo Finance）
    │                      │                    │
    │                      ├──→ /api/chat ──→ LangGraph ──→ ChromaDB ──→ Claude
    │                      │
    └──← 静态文件（HTML/CSS/JS）
```

## 海龟交易法则指标说明

| 指标 | 参数 | 说明 |
|------|------|------|
| 布林带 | 20周期, 2σ | 中轨=MA20，上下轨=±2个标准差，衡量波动范围 |
| ATR / N值 | 20周期 | 平均真实波幅，海龟用N值决定头寸规模（1N=账户的1%风险） |
| 唐奇安通道 系统1 | 20日高点/10日低点 | 短期突破信号 |
| 唐奇安通道 系统2 | 55日高点/20日低点 | 长期突破信号 |
