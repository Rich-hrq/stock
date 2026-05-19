# Feature: 并发请求处理改进

## 需求背景

当前项目所有 `async def` 端点内部执行了同步阻塞调用（yfinance、requests、LLM 推理、sentence_transformers 编码等），直接运行在 asyncio 事件循环上，导致 `async` 形同虚设。任何一个阻塞请求都会卡死所有其他并发请求。

## 需求总结

| 项目 | 决策 |
|------|------|
| 阻塞调用包装 | 使用 `asyncio.to_thread()` 将阻塞调用移出事件循环 |
| requests 替换 | `guardian_news`、`polymarket`、`proxy` 三个服务改用 `httpx.AsyncClient` |
| RAG 并发限制 | 添加 `asyncio.Semaphore(3)` |
| 线程池 | 使用 Python 默认 ThreadPoolExecutor |
| 部署变更 | 不做代码改动（仅建议） |

---

## 功能边界

### 做什么

- 将 yfinance、LLM 推理、pandas 计算等同步阻塞调用包装到 `asyncio.to_thread()` 中
- 将 `requests` 替换为 `httpx.AsyncClient`
- RAG 接口添加并发数限制
- 更新 `concurrency.md` 反映改进后的状态

### 不做什么

- 不改变接口签名（请求/响应格式不变）
- 不修改前端代码
- 不添加新的依赖包（`httpx` 已在依赖中）
- 不修改数据库连接池配置
- 不修改 Uvicorn 启动方式

---

## 核心设计

### 改进策略

```
改进前：
  async def endpoint():
      result = blocking_io_call()   # 阻塞事件循环！
      return result

改进后（方案 A — 服务层异步化）：
  # service 层：原函数保持不变或转为 async
  async def service_async():
      async with httpx.AsyncClient() as c:
          return await c.get(...)

  # router 层：
  async def endpoint():
      result = await service_async()  # 真正异步，不阻塞事件循环
      return result

改进后（方案 B — 线程池包装）：
  # service 层：保持同步函数 + 提供异步包装
  def sync_service(): ...
  async def sync_service_async():
      return await asyncio.to_thread(sync_service, ...)

  # router 层：
  async def endpoint():
      result = await sync_service_async()  # 在线程池中执行
      return result
```

### 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/services/guardian_news.py` | 修改 | `requests` → `httpx.AsyncClient`，函数改为 async |
| `backend/services/polymarket.py` | 修改 | `requests` → `httpx.AsyncClient`，函数改为 async |
| `backend/services/proxy.py` | 修改 | `requests` → `httpx.AsyncClient`，函数改为 async |
| `backend/services/market_data.py` | 修改 | 新增 `fetch_index_data_async()` 包装函数 |
| `backend/services/rag_v3.py` | 修改 | 新增 `ask_question_v3_async()` 包装函数 |
| `backend/services/news_summary.py` | 修改 | 新增 `generate_summary_async()` 包装函数 |
| `backend/routers/chat.py` | 修改 | 使用 async 包装 + 添加 Semaphore(3) |
| `backend/routers/guardian.py` | 修改 | `await` async 函数 |
| `backend/routers/prediction.py` | 修改 | `await` async 函数 |
| `backend/routers/proxy.py` | 修改 | `await` async 函数 |
| `backend/routers/index_data.py` | 修改 | 使用 async 数据获取，技术指标计算移入线程池 |
| `backend/routers/portfolio.py` | 修改 | 使用 `fetch_index_data_async()` |
| `concurrency.md` | 修改 | 更新分析文档反映改进后状态 |
| `stress_test.py` | 新增 | API 并发压力测试脚本 |
| `README.md` | 修改 | 添加并发测试章节，更新技术栈说明 |

---

## 实现计划

1. 修改 `services/guardian_news.py`：`requests` → `httpx.AsyncClient`
2. 修改 `services/polymarket.py`：`requests` → `httpx.AsyncClient`
3. 修改 `services/proxy.py`：`requests` → `httpx.AsyncClient`
4. 修改 `services/market_data.py`：新增 `fetch_index_data_async()`
5. 修改 `services/rag_v3.py`：新增 `ask_question_v3_async()`
6. 修改 `services/news_summary.py`：新增 `generate_summary_async()`
7. 修改 `routers/chat.py`：使用 async 包装 + Semaphore(3)
8. 修改 `routers/guardian.py`：await async 函数
9. 修改 `routers/prediction.py`：await async 函数
10. 修改 `routers/proxy.py`：await async 函数
11. 修改 `routers/index_data.py`：使用 async 数据获取 + 技术指标线程池化
12. 修改 `routers/portfolio.py`：使用 `fetch_index_data_async()`
13. 更新 `concurrency.md`：反映改进后的并发状态

---

## 风险与注意事项

- `httpx.AsyncClient` 已在项目依赖中（`exchange_rate.py` 已使用），无新增依赖
- yfinance 不支持 async，必须用线程池包装
- `sentence_transformers` 和 `chromadb` 的线程安全性：单 worker 下安全；线程池中执行需注意 GIL（CPU 密集型操作受 GIL 限制，但 IO 等待期间会释放 GIL）
- Semaphore 需在模块级别定义，跨请求共享
- `asyncio.to_thread()` 使用默认线程池，max_workers 由 Python 自动管理

---

## 最终确认记录

### 用户确认

- 改进范围：全部 4 条建议
- 线程池大小：使用默认
- RAG Semaphore：3

### 最终决策

- requests → httpx（方案 A）用于三个纯 HTTP 服务
- asyncio.to_thread（方案 B）用于 yfinance / LLM / pandas
- Semaphore(3) 仅限 RAG 接口

---

## 压力测试结果

运行 `python stress_test.py --concurrency 5,10,20 --requests 20` 共 360 个请求，100% 成功率。

### 纯异步接口

| 接口 | 并发=5 | 并发=10 | 并发=20 |
|------|--------|---------|---------|
| `/api/health` | 2430 req/s | 2185 req/s | 2242 req/s |
| `/api/indices` | 2177 req/s | 2255 req/s | 2285 req/s |
| `/api/market/status` | 2202 req/s | 2037 req/s | 2001 req/s |

吞吐保持 2000+ req/s，不随并发增加下降——事件循环未被阻塞。

### 线程池接口（yfinance + pandas）

| 并发 | `/api/indices/{symbol}/analysis` |
|------|----------------------------------|
| 5 | 6.9 req/s (avg 0.658s) |
| 10 | 10.7 req/s (avg 0.779s) |
| 20 | 19.9 req/s (avg 0.732s) |

吞吐随并发线性增长，线程池允许 yfinance 请求真正并行。

### 异步 HTTP 接口（httpx）

| 并发 | `/api/predict` | `/api/guardian_news` |
|------|---------------|---------------------|
| 5 | 9.1 req/s | 2.9 req/s |
| 10 | 15.7 req/s | 4.7 req/s |
| 20 | 30.4 req/s | 6.3 req/s |

predict 近线性扩展（9.1 → 30.4）；guardian_news 受上游限流影响增长趋缓。

### 结论

阻塞调用已完全移出事件循环。在 concurrency=20 的重压下，纯异步接口依然 2000+ req/s，证明并发改进生效。
