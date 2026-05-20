# Feature: 美股指数技术分析

## 需求背景

需要一个美股指数技术分析工具，支持多指数、多时间周期、海龟交易法则指标，为投资决策提供技术面参考。

## 需求总结

| 项目 | 决策 |
|------|------|
| 数据源 | yfinance（Yahoo Finance） |
| 支持的指数 | 标普500、纳斯达克100、纳斯达克综合、道琼斯 |
| 图表库 | ECharts |
| 技术指标 | 布林带、ATR/N值、唐奇安通道(系统1+2)、MA(5/10/20) |
| 统计计算 | 起始价、当前价、最高/低价、区间涨跌、日涨跌、振幅、趋势 |

---

## 功能边界

### 做什么
- 展示四大美股指数的走势图，支持按时间范围缩放
- 提供 5 种图表模式：走势线、均线(MA5/10/20)、K线+成交量、布林带、唐奇安通道
- 计算并展示海龟交易法则核心指标
- 基于趋势跟踪策略自动生成投资建议文案
- 图表分组切换：走势线始终可见，其余按按钮独立切换（均线/K线+量/布林带/唐奇安/持仓标记）
- 动态内联图例，按可见系列实时更新
- 数据粒度自适应：同日用1h线，跨日用1d线

### 不做什么
- 不提供实时交易下单功能
- 不提供回测引擎
- 不自动执行交易建议

---

## 核心设计

### 数据流

```
浏览器 → GET /api/indices → 指数列表
浏览器 → GET /api/indices/{symbol}/analysis?start_date=&end_date=
    → services/market_data.py: yfinance.Ticker(symbol).history()
    → services/indicators.py: compute_bollinger/compute_atr/compute_ma/compute_donchian/judge_trend/generate_advice
    → 返回 { symbol, name, data[]（含ma5/ma10字段）, stats, advice }
前端 → charts.js: renderChart() + indicators.js: renderIndicators()
```

### 数据格式

数据记录按 `iloc[i]` 位置对齐，不依赖日期字符串。所有 DataFrame 共享同一 index。

### 统计指标

| 指标 | 公式 |
|------|------|
| 起始价 | `df["open"].iloc[0]` |
| 当前价 | `df["close"].iloc[-1]` |
| 区间涨跌 (O→C) | `(当前价 − 起始价) / 起始价 × 100%` |
| 日涨跌 (P→C) | `(当前价 − 前日收盘) / 前日收盘 × 100%` |
| 区间振幅 | `(最高价 − 最低价) / 起始价 × 100%` |
| 当前趋势 | 价格≥20日高点→上升；≤20日低点→下降；否则盘整 |

---

## 边界条件

- 当日查询使用 `1h` K线，需等待开盘后有数据
- 非交易日（周末/节假日）无当日数据
- 网络需代理（国内访问 Yahoo Finance）

---

## 实现计划

1. 搭建 FastAPI + Uvicorn 基础框架
2. 实现 yfinance 数据获取（含代理支持、auto_interval）
3. 实现技术指标计算模块（indicators.py）
4. 实现前端 ECharts 图表渲染
5. 实现统计面板 + 投资建议面板
6. 新增图表分组切换系统（走势线/均线/K线+量/布林带/唐奇安）
7. 日线数据与 Yahoo Finance 对齐

---

## 文件变更清单

| 文件 | 操作 |
|------|------|
| `backend/main.py` | 新增 |
| `backend/config.py` | 新增 |
| `backend/routers/index_data.py` | 新增 |
| `backend/services/market_data.py` | 新增 |
| `backend/services/indicators.py` | 新增 |
| `backend/schemas.py` | 新增（后改为共用） |
| `frontend/index.html` | 新增 |
| `frontend/js/app.js` | 新增 |
| `frontend/js/charts.js` | 新增 |
| `frontend/js/indicators.js` | 新增 |
| `frontend/css/styles.css` | 新增 |

---

## 风险与注意事项

- yfinance 接口可能因 Yahoo 政策变更而不可用，可考虑 akshare 作为备选
- 国内环境必须配置 `all_proxy` 才能访问 Yahoo Finance
- MA20 系列被均线组和布林带组共享引用，两组同时开启时需去重避免重复绘制
