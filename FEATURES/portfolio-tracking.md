# Feature: 基金持仓记录

## 需求背景

在美股指数分析平台基础上，新增持仓记录功能。用户可以注册登录后，记录在四大美股指数上的买卖操作，系统自动查询收盘价和汇率，计算持仓份额、已实现盈亏和未实现盈亏。

## 需求总结

| 项目 | 决策 |
|------|------|
| 用户系统 | 注册/登录 + JWT Token（7天过期） |
| 密码加密 | bcrypt（passlib） |
| 支持的标的 | ^GSPC、^NDX、^IXIC、^DJI |
| 收盘价来源 | yfinance（复用 market_data.py） |
| 汇率来源 | open.er-api.com（免费，当前实时汇率） |
| 仓位计算 | 加权平均成本法 |
| 数据库 | MySQL（SQLAlchemy + aiomysql） |
| 前端 | 独立页面（portfolio.html，需登录） |

---

## 功能边界

### 做什么
- 用户注册/登录（JWT 鉴权）
- 记录买入/卖出交易（指数、方向、日期、人民币金额）
- 自动查询当日收盘价、汇率，计算美元等值和份额
- 持仓汇总：按指数分组，展示份额、加权成本、已实现净赚、预期盈亏
- 当日清仓预期盈亏计算
- 交易历史列表（按时间倒序）
- 删除交易（二次确认，自动重算）

### 不做什么
- 不支持自定义标的外币种
- 汇率只取当前实时值，不作历史回溯
- 不提供图表可视化（在主页走势线上叠加交易标记）
- 不导出报表

---

## 核心设计

### 用户系统

```
POST /api/auth/register → bcrypt(password) → INSERT users
POST /api/auth/login    → verify bcrypt → JWT(7d) → {access_token}
GET  /api/auth/me       → 验证 JWT → {id, username, created_at}
```

- 未登录用户正常使用原有功能，不受影响
- 已登录用户额外访问持仓功能
- 每用户只能看自己的数据（user_id 隔离）

### 交易记录

```
POST   /api/portfolio/transactions       → 新增交易（自动计算收盘价+汇率）
GET    /api/portfolio/transactions       → 用户所有交易（按日期倒序）
DELETE /api/portfolio/transactions/{id}  → 删除 → 重算
GET    /api/portfolio/summary            → 持仓汇总（含盈亏）
GET    /api/portfolio/transactions/markers → 图表交易标记（主页走势线叠加）
```

### 计算逻辑

**买入：**
```
新增份额 = 人民币金额 ÷ 汇率 ÷ 当日收盘价
总份额 += 新增份额
总成本 += 人民币金额
```

**卖出：**
```
卖出份额 = 人民币金额 ÷ 汇率 ÷ 当日收盘价
总份额 -= 卖出份额
总成本 -= (加权平均成本 × 卖出份额)
已实现收益 = 卖出金额 - (加权平均成本 × 卖出份额)
```

**加权平均成本：**
```
加权平均成本 = 总成本 ÷ 总份额
```

**当日清仓预期：**
```
清仓价值 = 总份额 × 当前收盘价 × 当日汇率
未实现盈亏 = 清仓价值 - 当前持仓成本
总盈亏 = 已实现净赚 + 未实现盈亏
```

### 权限隔离
- 未登录：所有原有功能正常使用
- 已登录：额外可访问持仓记录
- 导航栏：仅在 portfolio.html 显示登录状态，其他页面不感知

---

## 边界条件

- 收盘价非交易日时取最近一个交易日
- 汇率使用当前实时值（免费 API 不支持历史）
- 用户可手动修改汇率字段
- 卖出份额超过持仓时提示错误
- 定投计划执行时若当日无行情则跳过
- MySQL 不可用时持仓模块不可用（不影响其他功能）

---

## 实现计划

1. 设计 users + transactions 表（MySQL）
2. 实现用户认证（bcrypt + JWT）
3. 实现交易 CRUD + 自动查询收盘价/汇率
4. 实现持仓汇总盈亏计算（加权平均成本法）
5. 前端：登录/注册表单 → 持仓汇总 → 交易表单 → 交易历史
6. 主页走势线叠加交易标记
7. 新增定投计划（见 dca-investment-plans.md）

---

## 文件变更清单

| 文件 | 操作 |
|------|------|
| `backend/models.py` | 新增 users + transactions 表 |
| `backend/database.py` | 新增（异步 MySQL 引擎） |
| `backend/auth.py` | 新增（JWT + bcrypt） |
| `backend/routers/auth.py` | 新增 |
| `backend/routers/portfolio.py` | 新增 |
| `backend/services/exchange_rate.py` | 新增（汇率 API） |
| `backend/schemas.py` | 新增认证/交易/持仓 Pydantic 模型 |
| `frontend/portfolio.html` | 新增 |
| `frontend/js/portfolio.js` | 新增 |
| `frontend/css/portfolio.css` | 新增 |

---

## 风险与注意事项

- bcrypt/passlib 兼容性问题：passlib 1.7+ 的 bcrypt 方案需指定正确的 backend
- MySQL 密码含特殊字符需 URL 编码（urllib.parse.quote_plus）
- uvicorn 未重启导致新路由 404
- 交易历史删除后立即重算，无需手动刷新
