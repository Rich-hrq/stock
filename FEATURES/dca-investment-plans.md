# Feature: 定投计划

## 需求背景

在持仓记录功能基础上，新增自动定投计划。用户可以设置每周或每月自动买入指定指数，系统到期自动执行，无需手动操作。

## 需求总结

| 项目 | 决策 |
|------|------|
| 频率 | 每周（指定周几）或每月（指定日期） |
| 默认金额 | ¥200 |
| 防重复 | 幂等设计，同一天不重复执行 |
| 管理 | 暂停/启用、修改、删除 |
| 执行方式 | 前端点击"执行到期计划"，非 cron 自动触发 |

---

## 功能边界

### 做什么
- 创建定投计划（指数、金额、频率、执行日）
- 修改计划（金额、频率）
- 启用/暂停计划
- 删除计划
- 手动执行到期计划（幂等防重复）

### 不做什么
- 不自动在后台执行（非 cron/server-side scheduler）
- 不支持按小时/按日定投
- 不检查账户余额

---

## 核心设计

### API

```
GET    /api/portfolio/plans              → 用户所有定投计划
POST   /api/portfolio/plans              → 新增计划
PUT    /api/portfolio/plans/{id}         → 修改计划
PATCH  /api/portfolio/plans/{id}/toggle  → 启用/暂停
DELETE /api/portfolio/plans/{id}         → 删除计划
POST   /api/portfolio/plans/execute      → 执行所有到期计划
```

### 幂等设计

执行时检查 `last_executed` 字段：
- 同日已执行 → 跳过
- 新日期 → 自动新增交易记录 → 更新 last_executed

### 执行规则
- 每周：检查当天是否与 `day_of_week` 匹配，且上次执行日期 < 今天
- 每月：检查当天是否与 `day_of_month` 匹配，且上次执行日期 < 今天
- 暂停的计划不执行

---

## 边界条件

- 执行日赶上非交易日 → 取最近交易日收盘价
- 执行日无网络 → 跳过（不补执行）
- 多个计划同时到期 → 全部执行
- 计划被删除 → 已执行的交易不受影响

---

## 文件变更清单

| 文件 | 操作 |
|------|------|
| `backend/models.py` | 新增 investment_plans 表 |
| `backend/routers/portfolio.py` | 新增 plans 相关路由 |
| `backend/schemas.py` | 新增 InvestmentPlanCreate/Out |
| `frontend/js/portfolio.js` | 新增定投计划 UI 逻辑 |

---

## 风险与注意事项

- 依赖用户主动点击执行按钮，不会自动触发
- 星期几用 0=Monday..6=Sunday（Python 默认）
- 月定投日期建议限制 1-28 避免月末问题
