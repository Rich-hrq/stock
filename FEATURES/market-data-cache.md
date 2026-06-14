# Feature: 美股数据文件缓存

## 需求总结

| 维度 | 决策 |
|------|------|
| 缓存范围 | 所有通过 `fetch_index_data_async` 的 yfinance API 调用 |
| 缓存 Key | `(symbol, start_date, end_date, interval)` 四元组取 MD5 前 16 位 |
| 存储格式 | Pickle（`pd.to_pickle` / `pd.read_pickle`），零额外依赖 |
| 有效期 | 当天有效（`cached_at.date() == today.date()`），次日自动过期 |
| 缓存目录 | `backend/cache/market_data/` |
| 并发策略 | 先写 `.tmp` 再 `os.replace` 原子替换 |
| 清理策略 | 每次写入时删除超过 7 天的缓存文件 |
| 错误策略 | 读失败/损坏 → 忽略缓存走 API；写失败 → log warning 不影响返回；空数据不缓存 |

## 功能边界

**做什么**：
- 同一天内对同一 `(symbol, start_date, end_date, interval)` 的重复请求，只第一次调用 yfinance API，后续直接读缓存
- 次日自动过期，重新拉取最新数据
- 所有现有调用方（主页图表、持仓汇总、交易创建、定投执行）自动受益

**不做什么**：
- 不做跨天缓存
- 不做内存缓存（LRU/TTL）
- 不做智能日期范围合并
- 不做 Redis 集中缓存
- 不提供手动清除缓存的 API（后续可加）
- 不缓存空数据（yfinance 返回空 DataFrame）

## 核心设计

### 文件结构

```
backend/cache/market_data/
├── a1b2c3d4e5f6g7h8.pkl       # DataFrame 数据（Pickle 格式）
├── a1b2c3d4e5f6g7h8.meta.json # 元数据
└── ...
```

### 元数据格式 (`.meta.json`)

```json
{
  "symbol": "^GSPC",
  "start_date": "2025-12-17",
  "end_date": "2026-06-14",
  "interval": "1d",
  "cached_at": "2026-06-14T10:30:00.123456"
}
```

### 缓存读写流程

```
fetch_index_data_async(symbol, start, end, interval)
  │
  ├─ cache_enabled? ──No──→ fetch_index_data() → return df
  │
  ├─ _read_cache(key) ──hit──→ return cached_df
  │
  └─ miss:
      ├─ fetch_index_data() → df
      ├─ if df not empty: _write_cache(key, df)
      ├─ _cleanup_old_cache()
      └─ return df
```

### 缓存 Key 生成

```python
import hashlib

def _cache_key(symbol, start_date, end_date, interval):
    raw = f"{symbol}|{start_date}|{end_date}|{interval}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]
```

## 实现计划

### 步骤 1：添加配置 (`config.py`)
- 新增 `MARKET_DATA_CACHE_DIR`
- 新增 `MARKET_DATA_CACHE_ENABLED`
- 新增 `MARKET_DATA_CACHE_MAX_AGE_DAYS`

### 步骤 2：实现缓存核心 (`services/market_data.py`)
- 新增 `_cache_key()` — 生成文件名字符串
- 新增 `_read_cache()` — 读取缓存，命中返回 DataFrame，未命中返回 None
- 新增 `_write_cache()` — 写入 .tmp 临时文件 + 原子替换为 .pkl，同时写 .meta.json
- 新增 `_cleanup_old_cache()` — 遍历目录删除超过 N 天的缓存文件
- 修改 `fetch_index_data_async` — 在调用 `fetch_index_data` 前插入缓存检查

### 步骤 3：更新 `.gitignore`
- 添加 `backend/cache/`

### 步骤 4：更新 `DEBUG.md`
- 记录缓存机制设计和使用注意事项

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/config.py` | 修改 | 新增 3 行缓存配置常量 |
| `backend/services/market_data.py` | 修改 | 新增 4 个缓存函数 + 修改 `fetch_index_data_async` |
| `.gitignore` | 修改 | 新增 `backend/cache/` |
| `DEBUG.md` | 修改 | 新增缓存设计记录 |
| `FEATURES/market-data-cache.md` | 新增 | 本功能文档 |

## 测试结果

### 单元测试
- ✅ `test_cache_key_deterministic` — 相同参数产生相同 key，不同 interval 产生不同 key
- ✅ `test_read_miss` — 不存在的缓存返回 None
- ✅ `test_write_and_read` — 写入后正确读取，行数和列名一致
- ✅ `test_cleanup` — 清理操作无异常
- ✅ `test_empty_df_not_cached` — 空 DataFrame 不会被缓存

### 端到端测试（真实 yfinance API）

| 指标 | 数值 |
|------|------|
| 第一次调用（API） | 0.58s |
| 第二次调用（缓存命中） | 0.0002s |
| 加速比 | **2630x** |
| 数据一致性 | 完全一致 (`df.equals() == True`) |

1. **Pickle 版本兼容**：缓存文件包含 pandas DataFrame，若 pandas 大版本升级可能导致读取失败。已通过 try/except 保护，读失败自动回退 API。
2. **磁盘空间**：每个缓存文件约 50-200KB（按 180 天日线数据估算），7 天自动清理上限约 100 个文件 ≈ 20MB，风险低。
3. **多 worker 不共享**：当前单 worker 部署无此问题。若扩展为多 worker，每个 worker 各自维护文件缓存，可能产生重复 API 请求。文件缓存天然支持跨进程共享（读同一个文件），无需额外处理。
4. **缓存目录首次创建**：第一次写入时自动 `os.makedirs(exist_ok=True)`，无需手动创建。
