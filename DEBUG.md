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

## Nginx 静态文件 403 Forbidden

**现象**：nginx 配置了直接 serve 静态文件（CSS/JS/HTML），但浏览器访问返回 403

**原因**：nginx worker 进程以 `www-data` 用户运行，而项目目录在 `/home/<user>/stock-turtle/...` 下。Ubuntu 默认 `/home/<user>` 权限为 750（`rwxr-x---`），`www-data` 无法穿越（无 execute 权限进入用户目录）

**解决**：去掉 nginx 配置中的静态文件 `location` 块，所有请求统一反向代理到 uvicorn。静态文件优化对于此类小规模部署并非必要

---

## Nginx 反向代理必须透传的 Header

**注意**：通过 nginx 代理后，若不设置以下 header，后端日志中的客户端 IP 会全部显示 127.0.0.1

**必须设置**（每个 `location` 块都要加）：
```nginx
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
```

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
cd ~/stock-turtle
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

## Git merge 后 uvicorn 未重启导致 404

**现象**：`git merge` 后重新加载 nginx，所有页面返回 404，但 `/api/health` 和 `/docs` 正常。

**原因**：uvicorn 启动时未加 `--reload` 参数，进程常驻内存，加载的是旧代码。本次 merge 中 `config.py` 的 `STATIC_DIR` 从 `backend/static/`（已删除）变更为 `frontend/`，旧进程仍查找不存在的目录，所有静态文件请求都返回 404。

**解决**：
```bash
# 1. 找到 uvicorn 进程并杀死
pkill -f "uvicorn backend.main"

# 2. 确认端口释放
lsof -ti:8000 | xargs kill -9

# 3. 用正确的 conda 环境重启（uvicorn 装在 stock 环境，非 base）
conda activate stock
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
```

**教训**：长时间运行的服务若未开启 `--reload`，merge 或 pull 新代码后需要手动重启。

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
~/.stock/bin/python -m uvicorn backend.main:app --reload --port 8000
```

**验证**：启动后测试摘要接口：
```bash
curl -s -X POST http://localhost:8000/api/news/summary \
  -H "Content-Type: application/json" \
  -d '{"headlines": [{"title": "test", "link": "https://www.theguardian.com/world/2026/may/14/test"}]}'
```

---

## 新闻摘要 nginx 504 超时 — LLM 推理耗时超 60s

**现象**：不同设备访问新闻资讯页，部分成功生成摘要，部分返回：
```
摘要生成失败：Unexpected token '<', "<html> <h"... is not valid JSON
```
nginx 错误日志：`upstream timed out (110: Connection timed out) while reading response header`

**原因**：三层叠加 —
1. nginx 默认 `proxy_read_timeout=60s`，LLM 推理（36 条标题 + `deepseek-v4-pro` + `max_tokens=4096`）耗时 **91 秒**
2. `_get_llm()` 单例在 uvicorn auto-reload 后不更新参数，`default_request_timeout` 未生效
3. 无并发控制，多设备同时访问时 DeepSeek API 可能限流触发重试风暴

**解决**（2026-05-20）：
1. **nginx**：`/api/news/summary` 单独设置 `proxy_read_timeout 120s`
2. **后端 `news_summary.py`**：
   - `_get_llm()` 移除单例守卫，每次重建实例确保参数最新
   - `asyncio.wait_for(timeout=50)` 硬超时兜底
   - `asyncio.Semaphore(2)` 限制并发 LLM 调用
   - `MAX_HEADLINES=25` 截断标题列表
   - `max_tokens` 从 4096 降至 2048，减少生成耗时
   - 模型从 `deepseek-v4-pro` 切换为 `deepseek-v4-flash`（速度优先）
   - 新增 `SummaryError` 错误分类（apikey / timeout / ratelimit / model / network）
3. **前端 `news.js`**：
   - 检查 `Content-Type` 再 `res.json()`，避免 HTML 解析报错
   - `/api/health` 扩展返回模型名，页面加载时立即显示
   - 新增红色诊断面板，展示具体错误原因和排查建议
4. **`/api/health`** 扩展返回 `model` + `provider` 字段

**验证**：36 条标题从 91s 降至 29.7s，摘要 563 字，模型 `deepseek-v4-flash`。

---

## 前端静态文件被浏览器缓存，修改后页面无变化

**现象**：修改 JS/CSS 文件后刷新页面，功能无变化。

**原因**：浏览器缓存了旧版本的静态资源。

**解决**：强制刷新（`Cmd+Shift+R`），或打开 DevTools → Network → Disable cache。

---

## ECharts 分组切换：`series.show` 与 `setOption` 合并行为导致切换失效

**现象**：图表分组切换按钮点击后，线条不隐藏/不显示；或默认应隐藏的 K 线+量/布林带/唐奇安全部同时显示。

**原因**：
1. `series.show: false` 在某些 ECharts 版本中不可靠，无法保证系列被隐藏
2. 使用 `chart.setOption({ series: [...] }, false)`（默认合并模式）更新部分系列时，ECharts 按 `name`/`id` 匹配系列进行合并，但不会移除旧 option 中存在而新 option 中不存在的系列——导致隐藏的系列无法被移除

**解决**：
1. 将各分组的 series 定义缓存在 `cachedGroups` 对象中，每次切换时从缓存重建完整的可见 series 数组
2. 切换时始终使用 `chart.setOption(fullOption, true)`（`notMerge=true`），确保旧系列被完全替换
3. 非 series 部分的配置（grid/xAxis/yAxis/tooltip）缓存在 `cachedBaseOption` 中，通过 `Object.assign({}, cachedBaseOption, { series: visibleSeries })` 拼装完整 option

---

## 持仓记录功能：MySQL 本地配置与测试

**背景**：`563dc52` 提交新增了持仓记录功能（用户注册/登录 + 交易记录 + 持仓盈亏），但未测试，需配置 MySQL 环境变量后才能验证。

### MySQL 用户认证方式确认

**现象**：`mysql -u root` 报 `ERROR 1698 (28000): Access denied for user 'root'@'localhost'`

**原因**：MySQL 默认使用 `auth_socket` 插件认证 root 用户，不验证密码，而是校验操作系统用户身份。只有 OS root 用户才能免密登录 MySQL root。

**解决**：
```bash
sudo mysql -u root   # 使用 sudo 以 OS root 身份连接
```
或创建专用用户（如 `stock`@`localhost`）用于应用连接。

### 密码含特殊字符导致数据库连接失败

**现象**：注册接口返回 500，服务端报错 `Can't connect to MySQL server on 'stock@127.0.0.1'`

**原因**：MySQL 密码中包含 `@` 字符，在构建 SQLAlchemy 连接 URL 时（`mysql+aiomysql://user:password@host`），密码中的 `@` 被错误解析为 userinfo 与 host 的分隔符，导致主机名变为 `password_suffix@127.0.0.1`。

**解决**：在 `database.py` 的 `_build_url()` 中使用 `urllib.parse.quote_plus` 对用户名和密码进行 URL 编码：
```python
from urllib.parse import quote_plus
user = quote_plus(MYSQL_USER)
password = quote_plus(MYSQL_PASSWORD)
```

### passlib 与 bcrypt 5.x 不兼容

**现象**：注册接口返回 500，服务端报错 `ValueError: password cannot be longer than 72 bytes, truncate manually if necessary`

**原因**：`passlib>=1.7.4` 与 `bcrypt>=5.0.0` 不兼容。bcrypt 5.x 的 `hashpw` 函数增加了密码长度上限校验（72 字节），passlib 内部调用时传入的 bytes 对象长度超过限制，触发异常。

**解决**：
1. 移除 `passlib` 依赖，改用 `bcrypt` 原生 API：
```python
import bcrypt

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
```
2. `requirements.txt` 中固定 `bcrypt<4.1`（防止未来 5.x 被安装）。
3. 新增 `python-dotenv>=1.0.0` 依赖，在 `main.py` 顶部调用 `load_dotenv()` 自动加载 `.env`。

## 走势线交易标记看不到 — `closeLine` 引用在变量定义之前

**现象**：主页图表走势线上没有 buy/sell 标记，浏览器 Console 有 `TypeError: Cannot read properties of undefined`。

**原因**：在 `charts.js` 中构建 markPoint data 时引用了 `closeLine[idx]`，但 `closeLine` 变量在后面的数据提取步骤才定义。markPoint 构建代码的位置（日期格式化之后）早于数据提取（`records.map(r => r.close)`）。

**解决**：将 markPoint 构建代码移到最后（`cachedGroups.price` 之前、数据提取之后），确保 `closeLine` 已定义。

---
### .env 文件不生效

**现象**：在 `backend/.env` 中配置了 MySQL 环境变量，启动后 `MYSQL_HOST` 仍为空，持仓模块不加载。

**原因**：`config.py` 通过 `os.environ.get()` 读取环境变量，但项目未加载 `.env` 文件到进程环境中。

**解决**：在 `main.py` 文件顶部（所有导入之前）添加：
```python
from dotenv import load_dotenv
load_dotenv()
```

---

## 移动端看不到交易标记 — 静默 catch 吞掉错误信息

**现象**：电脑端登录后主图走势线上能显示 buy/sell 标记，手机端登录后看不到。

**原因**：`app.js` 中拉取交易标记的 `fetch()` 外层 `catch {}` 为空块，网络错误、API 401/500 等全部静默忽略，用户和开发者都无法感知失败原因。手机端可能因网络延迟更高、浏览器缓存旧版 JS 等原因导致请求失败。

**解决**：
1. 在 `catch` 和 `!mRes.ok` 分支中添加 `console.warn/log` 输出
2. 在 `index.html` 图例区旁新增 `#markerHint` 可视元素，实时显示标记加载状态：
   - `✓ N 笔交易标记` — 成功
   - `当前范围无交易` — token 有效但时间范围内无匹配交易
   - 空白 — 未登录（无 portfolio_token）

**移动端调试方法**：
- 连接手机到电脑，Chrome 地址栏 `chrome://inspect` 远程调试 → 看 Console 日志
- Safari：手机设置 → Safari → 高级 → Web Inspector，Mac Safari → 开发 → 选择设备

---

## K线形态识别：初始阈值过严格导致零命中

**现象**：点击任意 K 线柱均显示"未检测到明显的 K 线形态"，浏览器 Console 日志显示 body/range 比 >5%、趋势判断为 false。

**原因**：初始阈值按教科书理想形态设定，与真实美股指数数据不匹配：
1. **十字星** 实体/波幅阈值 5%：标普 500 日线实体通常占比 15-30%，几乎从不出现 5% 以下的极端 Doji
2. **锤子/上吊线** 下影线 ≥2 倍实体 + 上影线 ≤10% 波幅：过于严格
3. **小/大实体判定** 阈值 0.35/1.5 倍平均实体：标准太窄
4. **趋势判断** 10 日 lookback + 仅依赖斜率：ma20（boll_middle）前 19 条记录为 null，导致 NaN；10 日大长导致短期趋势无法识别
5. **三乌鸦/三白兵** 收盘需在 25% 波幅内才算"接近极值"：实盘中 30-40% 更常见

**解决**（2026-05-20）：

| 参数 | 修正前 | 修正后 |
|------|--------|--------|
| 十字星 body/range | ≤5% | ≤15% |
| 小实体判定 | `< 0.35 × avgBody` | `≤ 0.55 × avgBody` |
| 大实体判定 | `> 1.5 × avgBody` | `≥ 1.2 × avgBody` |
| 锤子/上吊线下影线 | ≥2 倍实体 | ≥1.5 倍实体 |
| 锤子/上吊线上影线 | ≤10% 波幅 | ≤20% 波幅 且 ≤实体 |
| 趋势 lookback | 10 日（固定） | 5 日（默认）+ 首尾比较 fallback |
| 斜率计算 null 处理 | 产生 NaN 污染整体 | 跳过 null 逐点累加 |
| 三乌鸦/三白兵收盘极值 | ≤25% 波幅 | ≤35% |
| 星星形态中间 K 线 | body/range < 5% | body/range < 15% |

同时新增 `console.log` 诊断输出（`[K线分析]` 前缀），每次点击输出 OHLC、实体/波幅比、趋势判断结果、命中形态列表。

**教训**：教科书形态插图是手绘示意，实际市场数据远不如示意图标准。阈值应从实盘数据反推校准，而非从示意图臆测。

---

## 市场数据文件缓存

**背景**：每次页面加载、持仓查询都会调用 yfinance API 拉取美股数据。同一天内股价不变（尤其是收盘后），重复请求浪费带宽和时间。

**解决**（2026-06-14）：
- 在 `fetch_index_data_async` 中加入文件缓存层
- 缓存 Key：`MD5(symbol|start_date|end_date|interval)` 前 16 位
- 缓存格式：Pickle（数据 `.pkl`）+ JSON（元数据 `.meta.json`）
- 有效期：当天有效（`cached_at.date() == today.date()`），次日自动过期
- 存储位置：`backend/cache/market_data/`（已加入 `.gitignore`）
- 并发安全：先写 `.tmp` 临时文件，再 `os.replace` 原子替换
- 清理策略：每次写入时删除超过 7 天未修改的缓存文件

**配置项**（`config.py`）：
```python
MARKET_DATA_CACHE_DIR = BACKEND_DIR / "cache" / "market_data"
MARKET_DATA_CACHE_ENABLED = True
MARKET_DATA_CACHE_MAX_AGE_DAYS = 7
```

**注意事项**：
- 缓存仅在 `fetch_index_data_async` 层生效，直接调用同步 `fetch_index_data` 不经过缓存
- 缓存文件损坏或版本不兼容时自动回退到 API，不影响正常功能
- yfinance 返回空 DataFrame 时不写入缓存，避免缓存"无数据"状态
- 如需强制刷新，删除 `backend/cache/market_data/` 目录下对应文件即可
