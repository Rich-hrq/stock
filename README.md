<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/LangGraph-RAG-ff6f00?style=for-the-badge&logo=langchain&logoColor=white" alt="RAG">
  <img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge" alt="License">
  <img src="https://img.shields.io/badge/status-active-success?style=for-the-badge" alt="Status">
</p>

<h1 align="center">📈 Stock Turtle</h1>
<h3 align="center">美股指数技术分析 & 海龟交易法则 RAG 智能问答系统</h3>

<p align="center">
  一个集技术图表、AI 问答、预测市场、新闻资讯与持仓管理于一体的<br/>
  全栈美股分析平台 — 基于 FastAPI + LangGraph + ECharts
</p>

---

## ✨ 功能亮点

<table>
  <tr>
    <td width="50%">

### 📊 技术分析
- **四大美股指数** — 标普500 / 纳斯达克100 / 纳斯达克综合 / 道琼斯
- **多时间级别** — 从日内到年线，自由缩放
- **5 种图表模式** — 走势线 / 均线(MA5/MA10/MA20) / K线+成交量 / 布林带 / 唐奇安通道
- **K线形态识别** — 点击 K 线柱自动识别 12 种经典形态（锤子线/吞没/十字星/三白兵等），附带完整讲解
- **海龟交易法则指标** — ATR/N值、布林带、唐奇安突破信号、趋势判断
- **自动投资建议** — 基于趋势跟踪策略生成操作参考
- **交易标记叠加** — 登录后在走势线上叠加买卖标记与金额

    </td>
    <td width="50%">

### 🧠 AI 智能
- **RAG 智能问答** — 基于《海龟交易法则》原书 PDF 的语义检索与生成
- **LangGraph v3 流水线** — 智能评估 → 选择性扩展 → 多查询融合检索
- **多 LLM 兼容** — 支持 Claude / DeepSeek 等 Anthropic 兼容 API
- **AI 新闻摘要** — 自动抓取 The Guardian 头条并生成当日简报

    </td>
  </tr>
  <tr>
    <td width="50%">

### 🌐 市场资讯
- **Polymarket 预测市场** — 按事件分组翻页，关键词高亮，概率条可视化
- **The Guardian 新闻** — 爬取最新报道，分类标签展示，原文链接跳转
- **反向代理** — 安全访问新闻原文，base 标签注入 + 域名白名单

    </td>
    <td width="50%">

### 💼 持仓管理
- **交易记录** — 登录后记录买卖操作，自动查询收盘价与汇率
- **持仓盈亏** — 加权平均成本法自动计算浮动盈亏
- **定投计划** — 设置每周/每月自动买入，到期自动执行，幂等防重复
- **市场状态指示器** — 双时区展示盘前/盘中/盘后/休市，自动识别夏令时

    </td>
  </tr>
</table>

---

## 📸 界面预览

> 🚧 截图即将更新 — 欢迎提交 PR 贡献界面截图！

<details>
<summary>点击展开界面说明</summary>

| 页面 | 路由 | 说明 |
|------|------|------|
| 主页（指数分析） | `/` | 多指数走势图 + 技术指标面板 + 投资建议 + RAG 聊天 |
| 预测市场 | `/prediction.html` | Polymarket 事件浏览与筛选 |
| 新闻资讯 | `/news.html` | Guardian 新闻列表 + AI 摘要 |
| 持仓记录 | `/portfolio.html` | 交易管理 + 定投计划（需登录） |
| API 文档 | `/docs` | Swagger UI 交互式 API 文档 |

</details>

---

## 🏗️ 技术架构

```
浏览器 ──── FastAPI ──── /api/indices/*  ──── yfinance (Yahoo Finance)
   │              │
   │              ├── /api/chat ──── LangGraph ──── ChromaDB ──── LLM
   │              │      ├─ v1: retrieve → generate
   │              │      ├─ v2: rewrite → retrieve → judge → 条件路由
   │              │      └─ v3: evaluate → 选择性扩展 → 多查询融合 → generate
   │              │
   │              ├── /api/predict ──── Polymarket API
   │              ├── /api/guardian_news ──── The Guardian
   │              ├── /api/news/summary ──── LLM (当日摘要)
   │              ├── /api/proxy ──── Guardian 反向代理
   │              ├── /api/market/status ──── 双时区 + 夏令时
   │              ├── /api/auth/* ──── MySQL + JWT
   │              └── /api/portfolio/* ──── MySQL + yfinance + 汇率API
   │
   └── 前端静态文件 (HTML / CSS / JS + ECharts)
```

### 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| **后端框架** | FastAPI + Uvicorn | 高性能异步 Web 框架 |
| **数据源** | yfinance | 美股指数 OHLCV 实时数据 |
| **AI / RAG** | LangGraph + ChromaDB + sentence-transformers | 多策略 RAG 流水线 + 本地向量检索 |
| **LLM** | langchain-anthropic | 兼容 Claude / DeepSeek 等模型 |
| **数据库** | SQLAlchemy + aiomysql + MySQL | 异步 ORM + 用户/交易持久化 |
| **认证** | JWT + bcrypt | Token 签发/验证 + 密码哈希 |
| **前端图表** | ECharts | 走势线 / K线 / 布林带 / 唐奇安通道 |
| **HTTP 客户端** | httpx (AsyncClient) | 全异步 HTTP（汇率、新闻、预测、代理） |

---

## 🚀 快速开始

### 前置要求

- **Python 3.12+**
- **MySQL**（持仓功能需要；纯图表分析可跳过）
- **网络代理**（国内环境访问 Yahoo Finance / HuggingFace 需要）

### 1. 克隆项目

```bash
git clone https://github.com/<your-username>/stock-turtle.git
cd stock-turtle
```

### 2. 创建虚拟环境

```bash
python3 -m venv .stock
source .stock/bin/activate
```

### 3. 安装依赖

```bash
pip install -r backend/requirements.txt
```

### 4. 配置环境变量

```bash
# 必需：LLM API Key（聊天功能）
export ANTHROPIC_AUTH_TOKEN="sk-ant-xxx"

# 可选：自定义 LLM（如使用 DeepSeek）
export ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
export ANTHROPIC_MODEL="deepseek-v4-pro[1m]"

# 可选：MySQL（持仓功能）
export MYSQL_HOST="127.0.0.1"
export MYSQL_USER="stock"
export MYSQL_PASSWORD="your-password"
export MYSQL_DATABASE="stock"
```

> 💡 推荐使用 `.env` 文件（放置在 `backend/` 目录下），`python-dotenv` 会自动加载。

### 5. 构建知识库（首次运行）

```bash
python backend/knowledge/ingest.py
```

> 读取《海龟交易法则》PDF（约256页），切片后向量化存入 ChromaDB。首次约需 2-3 分钟，后续无需重复。

### 6. 启动服务

```bash
# 开发模式（含代理）
all_proxy=http://127.0.0.1:7897 uvicorn backend.main:app --reload --port 8000

# 生产模式（后台运行）
all_proxy=http://127.0.0.1:7897 uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
```

### 7. 打开浏览器

| 页面 | 地址 |
|------|------|
| 🏠 主页 | http://localhost:8000 |
| 📈 预测市场 | http://localhost:8000/prediction.html |
| 📰 新闻资讯 | http://localhost:8000/news.html |
| 💼 持仓记录 | http://localhost:8000/portfolio.html |
| 📖 API 文档 | http://localhost:8000/docs |

### 🚢 可选：Nginx 反向代理部署

如果要将服务部署到服务器供外网访问，推荐在 uvicorn 前加一层 Nginx：

```bash
# 1. 安装 Nginx
sudo apt install nginx -y

# 2. 一键配置（使用项目提供的脚本）
sudo bash nginx_config/setup_nginx.sh

# 3. 修改配置中的 server_name 为你的服务器 IP
sudo sed -i 's/<your-server-ip>/你的IP/g' /etc/nginx/sites-available/stock

# 4. 启动后端（仅监听 127.0.0.1，不对外暴露）
uvicorn backend.main:app --host 127.0.0.1 --port 8000 &

# 5. 访问 http://你的IP
```

> 📖 详细配置原理及排查指南见 [`nginx_config/GUIDE.md`](nginx_config/GUIDE.md)

---

## 📡 API 一览

<details>
<summary>点击展开全部接口（共 22 个）</summary>

### 指数数据
| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/indices` | 可用指数列表 |
| `GET` | `/api/indices/{symbol}/analysis` | 完整技术分析（OHLCV + 指标 + 建议） |

### RAG 对话
| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/chat` | RAG 智能问答 |

### 预测市场 & 新闻
| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/predict` | Polymarket 预测数据 |
| `POST` | `/api/guardian_news` | Guardian 新闻爬取 |
| `POST` | `/api/news/summary` | AI 新闻摘要 |
| `GET` | `/api/proxy` | Guardian 反向代理 |

### 市场状态
| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/market/status` | 美股开休市状态（双时区） |

### 用户认证
| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/auth/register` | 用户注册 |
| `POST` | `/api/auth/login` | 用户登录 |
| `GET` | `/api/auth/me` | 当前用户信息 |

### 持仓交易
| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/portfolio/transactions` | 新增交易 |
| `GET` | `/api/portfolio/transactions` | 交易列表 |
| `DELETE` | `/api/portfolio/transactions/{id}` | 删除交易 |
| `GET` | `/api/portfolio/transactions/markers` | 图表交易标记 |
| `GET` | `/api/portfolio/summary` | 持仓汇总 |
| `GET` | `/api/portfolio/plans` | 定投计划列表 |
| `POST` | `/api/portfolio/plans` | 新增定投计划 |
| `PUT` | `/api/portfolio/plans/{id}` | 更新定投计划 |
| `PATCH` | `/api/portfolio/plans/{id}/toggle` | 启用/暂停定投 |
| `DELETE` | `/api/portfolio/plans/{id}` | 删除定投计划 |
| `POST` | `/api/portfolio/plans/execute` | 执行到期定投 |

### 系统
| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 健康检查 + 公开配置（模型名、提供商） |

</details>

---

## 📊 海龟交易法则指标

### 核心指标参数

| 指标 | 参数 | 说明 |
|------|------|------|
| **布林带** | 20周期, 2σ | 中轨=MA20，上下轨=±2个标准差 |
| **ATR / N值** | 20周期 | 平均真实波幅，海龟用N值决定头寸规模（1N = 账户1%风险） |
| **唐奇安系统1** | 20日高点 / 10日低点 | 短期突破信号 |
| **唐奇安系统2** | 55日高点 / 20日低点 | 长期突破信号 |

### 统计计算标准

| 指标 | 公式 | 说明 |
|------|------|------|
| 起始价 | `df["open"].iloc[0]` | 区间首根 K 线开盘价 |
| 当前价 | `df["close"].iloc[-1]` | 区间末根 K 线收盘价 |
| 最高价 / 最低价 | `max(high)` / `min(low)` | 区间内真实极值 |
| **区间涨跌 (O→C)** | `(当前价 − 起始价) / 起始价 × 100%` | 区间开盘到收盘的变化 |
| **日涨跌 (P→C)** | `(当前价 − 前日收盘) / 前日收盘 × 100%` | 对标 Yahoo Finance「% Change」 |
| 区间振幅 | `(最高价 − 最低价) / 起始价 × 100%` | 区间最大波动幅度 |
| 当前趋势 | 唐奇安通道突破判断 | 价格≥20日高点→上升；≤20日低点→下降；否则盘整 |

> 📐 数据粒度规则：同日查询使用 `1h` 线，跨日查询使用 `1d` 线。日线数据与 Yahoo Finance 网页端 OHLC 完全一致。

---

## 🔧 环境变量参考

| 变量 | 必需 | 说明 |
|------|:--:|------|
| `ANTHROPIC_AUTH_TOKEN` | ✅ | LLM API Key（也支持 `ANTHROPIC_API_KEY`） |
| `ANTHROPIC_BASE_URL` | - | 自定义 API 端点（DeepSeek 等兼容服务） |
| `ANTHROPIC_MODEL` | - | 模型名，默认 `claude-sonnet-4-6`。新闻摘要推荐 `deepseek-v4-flash`（速度优先） |
| `all_proxy` | ⭐ | HTTP 代理（国内访问外网需要） |
| `MYSQL_HOST` | ✅ | MySQL 地址，为空时禁用持仓模块 |
| `MYSQL_PORT` | - | MySQL 端口，默认 3306 |
| `MYSQL_USER` | ✅ | MySQL 用户名 |
| `MYSQL_PASSWORD` | ✅ | MySQL 密码（含特殊字符自动 URL 编码） |
| `MYSQL_DATABASE` | - | 数据库名，默认 `stock` |
| `JWT_SECRET` | - | JWT 签名密钥，默认 `dev-secret-change-me` |

> ✅ = 对应功能必需 &nbsp;&nbsp; ⭐ = 国内环境建议设置

---

## 🗂️ 项目结构

```
stock_website/
├── frontend/                     # 纯静态前端
│   ├── index.html                # 主页（指数分析 + 聊天）
│   ├── prediction.html           # 预测市场页
│   ├── news.html                 # 新闻资讯页
│   ├── portfolio.html            # 持仓记录页（需登录）
│   ├── css/                      # 页面样式
│   └── js/                       # 页面逻辑 + ECharts 图表 + K线形态识别
├── stress_test.py                 # API 并发压力测试脚本
├── concurrency.md                 # 并发请求处理分析文档
├── backend/                      # FastAPI 后端
│   ├── main.py                   # 应用入口
│   ├── config.py                 # 全局配置
│   ├── schemas.py                # Pydantic 模型
│   ├── database.py               # 数据库引擎
│   ├── models.py                 # ORM 模型
│   ├── auth.py                   # JWT + bcrypt
│   ├── routers/                  # API 路由层
│   │   ├── index_data.py         # 指数数据
│   │   ├── chat.py               # RAG 对话
│   │   ├── prediction.py         # 预测市场
│   │   ├── guardian.py           # 新闻爬取
│   │   ├── proxy.py              # 反向代理
│   │   ├── market_status.py      # 市场状态
│   │   ├── auth.py               # 用户认证
│   │   └── portfolio.py          # 持仓交易
│   ├── services/                 # 业务逻辑层
│   │   ├── market_data.py        # yfinance 数据获取
│   │   ├── indicators.py         # 技术指标计算
│   │   ├── polymarket.py         # 预测市场 API
│   │   ├── guardian_news.py      # 新闻爬虫
│   │   ├── news_summary.py       # AI 摘要
│   │   ├── proxy.py              # 反向代理
│   │   ├── market_status.py      # 交易时段
│   │   ├── exchange_rate.py      # 汇率查询
│   │   ├── rag.py                # RAG v1
│   │   ├── rag_v2.py             # RAG v2
│   │   └── rag_v3.py             # RAG v3（当前默认）
│   ├── knowledge/                # 知识库
│   │   ├── ingest.py             # PDF → ChromaDB 构建脚本
│   │   ├── test_rag.py           # RAG 版本对比测试
│   │   └── chroma_db/            # 向量数据库持久化
│   └── requirements.txt          # Python 依赖
├── nginx_config/                 # Nginx 反向代理配置
│   ├── nginx-stock.conf          # 站点配置模板
│   ├── setup_nginx.sh            # 一键部署脚本
│   └── GUIDE.md                  # Nginx 配置原理详解
├── FEATURES/                     # 功能设计档案（每功能一个 mini design doc）
│   ├── stock-index-analysis.md   # 美股指数技术分析
│   ├── rag-qa-system.md          # RAG 智能问答系统
│   ├── concurrency-improvements.md # 并发请求处理改进
│   ├── prediction-market.md      # Polymarket 预测市场
│   ├── guardian-news.md          # Guardian 新闻 + AI 摘要
│   ├── nginx-reverse-proxy.md    # Nginx 反向代理部署
│   ├── portfolio-tracking.md     # 持仓记录（用户系统+交易+P&L）
│   ├── dca-investment-plans.md   # 定投计划
│   ├── market-status-indicator.md # 市场状态指示器
│   ├── multi-llm-support.md      # 多 LLM 兼容
│   ├── frontend-backend-separation.md # 前后端分离重构
│   └── candlestick-pattern-analysis.md # K线形态识别与分析
├── README.md
├── guideline.md                  # 代码讲解 + 数据流说明
└── DEBUG.md                      # 踩坑记录
```

---

## 📚 功能档案

每个功能的完整设计文档存档于 [`FEATURES/`](FEATURES/) 目录，包含需求背景、数据结构、API 设计、边界条件与实现计划。适合了解功能的设计决策和约束。

---

## 🧠 RAG 流水线

项目实现了三代 RAG 策略，默认使用 v3：

| 版本 | 策略 | 特点 |
|------|------|------|
| **v1** | `retrieve → generate` | 基础检索增强生成 |
| **v2** | `rewrite → retrieve → judge → 条件路由` | 查询改写 + 相关性判断 |
| **v3** | `evaluate → 选择性扩展 → 多查询融合 → generate` | 智能评估 + 多查询融合检索（当前默认） |

运行对比测试：

```bash
python backend/knowledge/test_rag.py
# 结果输出到 knowledge/test_results.json 和 test_results.md
```

---

## 🔬 并发测试

项目已将所有阻塞调用（yfinance、requests、LLM、pandas）通过 `asyncio.to_thread()` 或 `httpx.AsyncClient` 移出事件循环，详见 [`concurrency.md`](concurrency.md)。

运行压力测试：

```bash
# 默认 3 个并发级别 (5/10/20)，每级别每接口 15 次请求
python stress_test.py

# 自定义参数
python stress_test.py --concurrency 5,10,20,30 --requests 30 --timeout 120
```

测试覆盖 6 个接口（排除 RAG），输出 min/max/avg/p50/p95/p99 延迟和吞吐量。

---

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

### 贡献方向

- 🎨 **UI/UX 改进** — 前端样式优化、移动端适配
- 📊 **新指标** — 更多技术指标（MACD、RSI、KDJ 等）
- 🌐 **新数据源** — 接入更多市场数据 API
- 🧠 **RAG 优化** — 检索策略改进、多模态支持
- 🐛 **Bug 修复** — 任何问题修复都欢迎

### 开发流程

```bash
# 1. Fork + Clone
git clone https://github.com/<your-username>/stock-turtle.git

# 2. 创建分支
git checkout -b feature/my-feature

# 3. 开发 & 测试

# 4. 提交 PR
```

> 💡 提交前请阅读 `DEBUG.md` 了解已知问题与踩坑记录。

---

## 📄 许可证

本项目采用 **MIT** 开源许可证 — 详见 [LICENSE](LICENSE) 文件。

---

<p align="center">
  <sub>Built with ❤️ using FastAPI · LangGraph · ECharts · yfinance</sub>
</p>
