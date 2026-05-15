"""美股指数分析网站 - FastAPI 应用入口。

启动方式：
    source .stock/bin/activate.fish
    uvicorn backend.main:app --reload --port 8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from .config import STATIC_DIR, MYSQL_HOST
from .routers import index_data, chat, prediction, guardian, proxy
from .routers import auth, portfolio


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化数据库表。"""
    if MYSQL_HOST:
        from .database import init_db
        await init_db()
    yield


app = FastAPI(
    title="美股指数波动分析 & 海龟交易法则问答",
    description="展示美股指数走势、布林带、ATR等海龟交易法则指标，支持RAG问答、持仓记录",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS — 前后端分离开发时允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 路由
app.include_router(index_data.router)
app.include_router(chat.router)
app.include_router(prediction.router)
app.include_router(guardian.router)
app.include_router(proxy.router)
app.include_router(auth.router)
app.include_router(portfolio.router)


@app.get("/api/health")
async def health():
    """健康检查。"""
    return {"status": "ok"}


# 静态文件托管（前端页面）
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
