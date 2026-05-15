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

---

## 统计指标用 close 系列代替完整 OHLC 四价

**现象**：1 天视图明明跌了，涨跌幅却显示绿色正数；振幅数值偏小。

**原因**：`index_data.py` 中统计指标的计算只用 `close` 列：
```python
close = df["close"]
start_price = close.iloc[0]           # 起价 = 第一小时收盘，不是开盘
max_price = close.max()               # 最高价 = 最高收盘价，漏了上影线
min_price = close.min()               # 最低价 = 最低收盘价，漏了下影线
```

**解决**：使用完整 OHLC 四价：
```python
start_price = df["open"].iloc[0]      # 起价 = 第一个开盘价
max_price   = df["high"].max()        # 最高价 = 真实日内最高
min_price   = df["low"].min()         # 最低价 = 真实日内最低
```

涨跌幅、振幅、最高/最低日期也相应从 `high`/`low` 列取值。

---

## 小时级 K 线数据在序列化时丢失（dict key 冲突）

**现象**：1 天视图（自动选择 1h 间隔）下，7 根小时 K 线只剩 1 根，且该 K 线的 OHLC 值与 stats 面板不一致。例如 stats 显示起价=29379，但图表只显示一根 open=29592 的 K 线。

**原因**：`index_data.py` 的 `df_to_records` 使用 `str(d.date())` 作为日期字段，同一日的 7 根小时 K 线全部获得相同的日期字符串 `"2026-05-14"`。后续 `dates_index` dict 以此字符串为 key，导致 7 根 K 线互相覆盖，最终只剩最后一根。stats 计算用的是原始 DataFrame（`df["open"].iloc[0]`），图表用的是被覆盖后的数据，两者不一致。

**解决**：
1. 移除 `df_to_records` 函数，改为直接遍历 DataFrame 按位置（`iloc[i]`）逐行构建记录
2. 日期字段改用 `idx_val.isoformat()` 保留完整时间（如 `2026-05-14T09:30:00-04:00`），确保每根 K 线有唯一 key
3. 所有技术指标（布林带/ATR/唐奇安）与 DataFrame 共享同一 index，通过相同的 `iloc[i]` 对齐取值
4. 前端 `charts.js` 新增日期格式化：同日数据显示 `HH:MM`，多日显示 `YYYY-MM-DD`

---

## yfinance 1h 与 1d 间隔的 OHLC 数据不一致

**现象**：网站 stats 与 Yahoo Finance 网页端显示的数值不一致。例如 `^NDX` 5 月 14 日：网站起价=29379.23，Yahoo Finance Open=29372.65（差 6.58 点）；网站最低价=29353.50，Yahoo Finance Low=29350.10（差 3.40 点）。

**原因**：`auto_interval` 对 ≤7 天的范围强制使用 `1h`（小时线），但 yfinance 的小时线数据和日线数据来源于 Yahoo 不同的数据端点，同一交易日的首根小时 K 线开盘价与日线开盘价存在微小差异。

**解决**：
1. 修改 `auto_interval`：同日查询（start==end）用 `1h`，跨日查询（start<end）统一用 `1d`
2. 日线数据与 Yahoo Finance 网页端 OHLC 完全一致
3. 新增「前日收盘」和「日涨跌 (P→C)」指标，与 Yahoo Finance 的 % Change 对齐

---

## ECharts K线图 tooltip 数据索引偏移

**现象**：悬浮提示中 OHLC 值显示为索引数字（0, 1, 2, 3…）而非实际价格。

**原因**：错误地将 K线 data 格式理解为 `[open, close, low, high]`（索引 0~3）。
实际 ECharts candlestick 系列的 tooltip `data` 格式为 `[dataIndex, open, close, low, high]`，
索引 0 是数据序号，索引 1~4 才是 OHLC 价格。

**解决**：tooltip 取值使用 `vals[1]`~`vals[4]`（开/收/低/高），不要用 `vals[0]`。

---

## AI 新闻摘要返回空字符串

**现象**：网页端「AI 今日摘要」区域显示空白，API `/api/news/summary` 返回 `{"summary":""}`

**原因**：服务器使用系统 Python（`/opt/homebrew/Cellar/python@3.12/...`）启动，而非 `.stock` 虚拟环境。系统 Python 环境中 `langchain_anthropic` 的版本或依赖与虚拟环境不同，导致 LLM 响应处理异常，`generate_summary()` 返回空字符串。

**解决**：始终使用 `.stock` 虚拟环境的 Python 启动服务器：
```bash
/Users/hrq/Coding/stock/.stock/bin/python -m uvicorn backend.main:app --reload --port 8000
```

**验证**：启动后测试摘要接口：
```bash
curl -s -X POST http://localhost:8000/api/news/summary \
  -H "Content-Type: application/json" \
  -d '{"headlines": [{"title": "test", "link": "https://www.theguardian.com/world/2026/may/14/test"}]}'
```

---

## 前端静态文件被浏览器缓存，修改后页面无变化

**现象**：修改 JS/CSS 文件后刷新页面，功能无变化。

**原因**：浏览器缓存了旧版本的静态资源。

**解决**：强制刷新（`Cmd+Shift+R`），或打开 DevTools → Network → Disable cache。
