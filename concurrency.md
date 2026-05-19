# 并发请求处理分析

## 整体架构

| 层级 | 技术 |
|------|------|
| Web 框架 | FastAPI (async) |
| ASGI 服务器 | Uvicorn（默认单 worker） |
| 数据库驱动 | SQLAlchemy 2.0 async + aiomysql |
| 连接池 | `pool_size=5` + `max_overflow=10` = 最多 15 并发连接 |
| HTTP 客户端 | `httpx.AsyncClient`（全部 HTTP 调用） |
| 阻塞调用处理 | `asyncio.to_thread()`（默认线程池） |
| 前端 | Static HTML/CSS/JS（FastAPI StaticFiles 挂载） |

## 并发模型

Uvicorn 默认单 worker 单进程，所有请求共享一个 asyncio 事件循环。`async def` 端点通过 `await` 协作式调度。

**改进后**：所有同步阻塞调用已通过以下两种方式移出事件循环：

- **策略 A — 替换为真正异步**：`requests` → `httpx.AsyncClient`（guardian_news, polymarket, proxy）
- **策略 B — 线程池包装**：`asyncio.to_thread()` 包装 yfinance / LLM / pandas 计算

---

## 按阻塞类型分类（改进后）

### 1. 纯异步接口（事件循环友好）

这类接口只做 `await` 操作，`await` 在等待 IO 时会自动让出事件循环给其他协程，支持真正的并发处理。

| 接口 | 方法 | 改进方式 | 并发能力 |
|------|------|----------|----------|
| `/api/health` | GET | 无 IO | 无限 |
| `/api/auth/register` | POST | 异步 DB | 受限于连接池 (15) |
| `/api/auth/login` | POST | 异步 DB | 受限于连接池 (15) |
| `/api/auth/me` | GET | 异步 DB | 受限于连接池 (15) |
| `/api/portfolio/transactions` | GET | 异步 DB | 受限于连接池 (15) |
| `/api/portfolio/transactions/{id}` | DELETE | 异步 DB | 受限于连接池 (15) |
| `/api/portfolio/transactions/markers` | GET | 异步 DB | 受限于连接池 (15) |
| `/api/portfolio/plans` | GET/POST/PUT/PATCH/DELETE | 异步 DB | 受限于连接池 (15) |
| `/api/guardian_news` | POST | `requests` → `httpx.AsyncClient` | 受限于网络 IO |
| `/api/predict` | POST | `requests` → `httpx.AsyncClient` | 受限于网络 IO |
| `/api/proxy` | GET | `requests` → `httpx.AsyncClient` | 受限于网络 IO |
| `/api/news/summary` | POST | `asyncio.to_thread()` 包装 LLM 调用 | 受限于默认线程池 |
| `/api/market/status` | GET | 纯计算，无 IO | 无限 |

### 2. 混合接口（异步 DB + 线程池包装的外部调用）

| 接口 | 方法 | 改进方式 | 并发能力 |
|------|------|----------|----------|
| `/api/portfolio/transactions` | POST | `fetch_index_data_async()` → `asyncio.to_thread(yfinance)` + async DB | 线程池 + 连接池 |
| `/api/portfolio/summary` | GET | `fetch_index_data_async()` × N + `await get_exchange_rate()` + async DB | 线程池 + 连接池 |
| `/api/portfolio/plans/execute` | POST | `fetch_index_data_async()` × M + async DB | 线程池 + 连接池 |

### 3. 线程池执行的接口（带并发控制）

| 接口 | 方法 | 改进方式 | 并发控制 |
|------|------|----------|----------|
| `/api/indices/{symbol}/analysis` | GET | `await fetch_index_data_async()` × 2 + `asyncio.to_thread(pandas 计算)` | 默认线程池 |
| `/api/chat` | POST | `await ask_question_v3_async()` → `asyncio.to_thread(RAG pipeline)` | `asyncio.Semaphore(3)` |

---

## 已实施的并发改进

### 策略 A：requests → httpx.AsyncClient

| 文件 | 函数 | 说明 |
|------|------|------|
| `services/guardian_news.py` | `scrape_guardian_news()` → `async def` | `requests.get()` → `httpx.AsyncClient.get()` |
| `services/polymarket.py` | `fetch_polymarket_data()` → `async def` | `requests.get()` → `httpx.AsyncClient.get()` |
| `services/proxy.py` | `fetch_page()` → `async def` | `requests.get()` → `httpx.AsyncClient.get()` |

### 策略 B：asyncio.to_thread() 包装

| 文件 | 异步包装函数 | 包装的同步调用 |
|------|-------------|---------------|
| `services/market_data.py` | `fetch_index_data_async()` | `yfinance` 网络请求 |
| `services/rag_v3.py` | `ask_question_v3_async()` | `sentence_transformers` + `chromadb` + LLM 推理 |
| `services/news_summary.py` | `generate_summary_async()` | LLM 推理 |
| `routers/index_data.py` | 局部 `_compute_analysis()` | 布林带 / ATR / 唐奇安 / 均线计算 |

### RAG 并发控制

`routers/chat.py` 添加 `asyncio.Semaphore(3)`，限制同时最多 3 个 RAG 请求进入线程池，防止 LLM API 限流触发。

---

## 剩余风险点

### 默认线程池容量

`asyncio.to_thread()` 使用 Python 默认 `ThreadPoolExecutor`（`max_workers=min(32, os.cpu_count()+4)`）。在高并发场景下，大量请求同时进入线程池可能导致线程竞争和内存压力。当前使用场景（单 worker、低并发）影响有限。

### 数据库连接池

`database.py:22-28`：

```python
engine = create_async_engine(
    _build_url(),
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)
```

- 最多 15 个并发数据库连接
- 多 worker 部署需注意 MySQL `max_connections` 限制

### 汇率缓存

`exchange_rate.py` 使用模块级全局变量缓存，单 worker 安全，多 worker 下缓存不共享。

### RAG 全局单例

`rag_v3.py` 的 `SentenceTransformer` / `chromadb` / `ChatAnthropic` 单例在多 worker 下每个进程独立加载，存在资源重复问题。`Semaphore(3)` 仅在单进程内生效。

---

## 总结

| 维度 | 改进前 | 改进后 | 状态 |
|------|--------|--------|------|
| 网络 IO (requests) | 阻塞事件循环 | `httpx.AsyncClient` 真正异步 | 已解决 |
| 网络 IO (yfinance) | 阻塞事件循环 | `asyncio.to_thread()` 线程池 | 已解决 |
| LLM 推理 | 阻塞事件循环 | `asyncio.to_thread()` 线程池 | 已解决 |
| pandas 计算 | 阻塞事件循环 | `asyncio.to_thread()` 线程池 | 已解决 |
| RAG 并发控制 | 无限并发 | `Semaphore(3)` | 已解决 |
| 数据库 | SQLAlchemy async | 未变 | 低风险 |
| 部署模式 | 单 worker | 未变 | 建议多 worker |

## 生产环境建议

考虑使用 `gunicorn` + `uvicorn.workers.UvicornWorker` 多 worker 部署：

```bash
gunicorn backend.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

注意事项：
- 多 worker 时需同步调高 MySQL `max_connections`（至少 `workers × (pool_size + max_overflow) + 10`）
- RAG `Semaphore(3)` 是单进程限制，4 worker 意味着最多 12 个并发 RAG 请求
- 汇率缓存在多 worker 下不共享，可考虑 Redis 集中缓存
