# Feature: Polymarket 预测市场

## 需求背景

接入 Polymarket 预测市场数据，让用户能查看与美股指数相关的市场预测事件和合约价格。

## 需求总结

| 项目 | 决策 |
|------|------|
| 数据源 | Polymarket API（官方 CLOB 接口） |
| 前端形式 | 独立页面（prediction.html），按事件分组翻页 |
| 交互 | 关键词/活跃日期双重高亮、概率条可视化 |
| 刷新方式 | 用户点击刷新按钮手动拉取 |

---

## 功能边界

### 做什么
- 从 Polymarket 拉取美股相关的预测市场事件
- 按事件（event）分组展示合约卡片
- 支持关键词高亮（nasdaq、s&p500 等）
- 高亮展示活跃日期（有合约过期的日期）
- 概率条可视化（彩色进度条显示 buy/sell 价格）
- 翻页浏览（每页一个 event）

### 不做什么
- 不下单/交易（只读模式）
- 不实时推送价格变化
- 不支持用户自定义筛选规则

---

## 核心设计

### API 流

```
POST /api/predict  { keywords, limit, threshold }
  → services/polymarket.py: 调用 Polymarket CLOB API
  → 按 event 分组 → 按 volume 排序
  → 返回分组后的市场数据
```

### 前端

```
prediction.html（独立页面，topbar + 翻页导航）
  prediction.js:
    - 每个 event 独占一个卡片，展示所有合约
    - 页码指示器：事件名 + 概率变化
    - 关键词高亮（标题中匹配到的关键词红色标记）
    - 活跃日期高亮（颜色+特殊样式）
    - 概率条：绿色(buy) / 红色(sell) 双色柱状图
```

---

## 边界条件

- Polymarket API 免费但有限速
- 部分事件可能无中文翻译
- 数据量大时需 limit 控制

---

## 文件变更清单

| 文件 | 操作 |
|------|------|
| `backend/routers/prediction.py` | 新增 |
| `backend/services/polymarket.py` | 新增 |
| `frontend/prediction.html` | 新增 |
| `frontend/js/prediction.js` | 新增 |
| `frontend/css/prediction.css` | 新增 |
| `backend/schemas.py` | 新增 PredictRequest |

---

## 风险与注意事项

- Polymarket API 不保证长期稳定，可能需要适配 API 变更
- 首次实现时卡片渲染覆盖翻页控件（fix: 调整 DOM 插入位置）
