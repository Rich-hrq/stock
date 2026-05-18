# Feature: 前后端分离重构

## 需求背景

项目初期前后端代码混在一起，随着功能增多需要解耦。将前端静态文件独立到 `frontend/` 目录，后端 API 独立到 `backend/` 目录，同时引入 Pydantic Schema 层规范接口数据格式。

## 需求总结

| 项目 | 决策 |
|------|------|
| 前端目录 | `frontend/`（HTML/CSS/JS 纯静态） |
| 后端目录 | `backend/`（FastAPI + routers + services） |
| 接口规范 | Pydantic schemas.py 统一管理 |
| 静态托管 | FastAPI StaticFiles 挂载 `/` |

---

## 核心设计

### 目录结构

```
frontend/          → 纯静态前端
  index.html       → 主页
  prediction.html  → 预测市场页
  news.html        → 新闻资讯页
  portfolio.html   → 持仓记录页
  css/             → 页面样式
  js/              → 页面逻辑

backend/           → FastAPI 后端
  main.py          → 应用入口
  config.py        → 全局配置
  schemas.py       → Pydantic 模型（所有 API 的数据格式）
  database.py      → 数据库引擎
  models.py        → ORM 模型
  auth.py          → JWT + bcrypt
  routers/         → API 路由层
  services/        → 业务逻辑层
  knowledge/       → RAG 知识库
```

### 模块分层

```text
routers/   → API 路由层（参数校验、响应组装）
services/  → 业务逻辑层（核心计算、外部 API 调用）
models.py  → ORM 模型（数据库表映射）
schemas.py → Pydantic 模型（请求/响应格式）
```

新增 API 原则：**先定义 Pydantic Schema，再编写 Router。**

---

## 文件变更清单

| 文件 | 操作 |
|------|------|
| `frontend/` | 新建目录，迁移静态文件 |
| `backend/` | 新建目录，拆分后端模块 |
| `backend/schemas.py` | 新增 |
| `backend/main.py` | 重构 |

---

## 风险与注意事项

- FastAPI StaticFiles 挂载在 `/`，API 路由必须在静态文件托管前注册
- CORS 中间件允许所有源（开发阶段），生产环境应限制
