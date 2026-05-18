# Feature: Guardian 新闻 + AI 摘要

## 需求背景

提供美股市场相关新闻资讯，从 The Guardian 爬取最新报道，支持分类浏览和 AI 摘要。

## 需求总结

| 项目 | 决策 |
|------|------|
| 新闻来源 | The Guardian（theguardian.com） |
| 爬取方式 | httpx + BeautifulSoup 服务端爬取 |
| 前端形式 | 独立页面（news.html），分类标签展示 |
| AI 摘要 | LLM 自动生成当日新闻简报 |
| 反向代理 | 安全访问原文，base 标签注入 + 域名白名单 |

---

## 功能边界

### 做什么
- 爬取 The Guardian 首页头条新闻
- 按分类标签（World、Business、Tech 等）展示
- 原文链接可通过反向代理安全访问
- AI 一键生成当日新闻摘要

### 不做什么
- 不爬取非 Guardian 来源
- 不存储新闻历史（每次刷新重新拉取）
- 不提供搜索/筛选功能

---

## 核心设计

### API 流

```
POST /api/guardian_news
  → services/guardian_news.py: httpx → BeautifulSoup 解析
  → 返回 [{title, link, category, summary}, ...]

POST /api/news/summary  { headlines }
  → services/news_summary.py: LLM 生成摘要
  → 返回 { summary, generated_at }
```

### 反向代理

```
GET /api/proxy?url=<Guardian原文URL>
  → services/proxy.py: 获取原文 → 注入 <base> 标签 → 返回
  → 仅在白名单域名内生效
```

### 前端

```
news.html（独立页面）
  news.js:
    - 分类标签横向排列
    - 新闻卡片：标题、摘要、时间、分类标签
    - AI 摘要按钮：一键生成当日头条摘要
    - 原文链接通过代理跳转
```

---

## 边界条件

- The Guardian 可能因地域限制不可用
- AI 摘要可能因 LLM 不可用而失败（返回空时前端提示）
- 代理仅对白名单域名生效

---

## 文件变更清单

| 文件 | 操作 |
|------|------|
| `backend/routers/guardian.py` | 新增 |
| `backend/services/guardian_news.py` | 新增 |
| `backend/services/news_summary.py` | 新增 |
| `frontend/news.html` | 新增 |
| `frontend/js/news.js` | 新增 |
| `frontend/css/news.css` | 新增 |
| `backend/schemas.py` | 新增 NewsSummaryRequest/Response |

---

## 风险与注意事项

- The Guardian 页面结构变化时需更新 BeautifulSoup 选择器
- AI 摘要为空时不影响新闻列表展示（兜底处理）
- 爬取频率不宜过高以避免 IP 被封
