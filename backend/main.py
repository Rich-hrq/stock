"""美股指数分析网站 - FastAPI 应用入口。

启动方式：
    source .stock/bin/activate.fish
    uvicorn backend.main:app --reload --port 8000
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware


from .config import STATIC_DIR
from .routers import index_data, chat, prediction, guardian, proxy

app = FastAPI(
    title="美股指数波动分析 & 海龟交易法则问答",
    description="展示美股指数走势、布林带、ATR等海龟交易法则指标，支持RAG问答",
    version="0.1.0",
)

# CORS — 前后端分离开发时允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 路由
# 把 routers 文件中的接口注册进来
app.include_router(index_data.router)
app.include_router(chat.router)
app.include_router(prediction.router)
app.include_router(guardian.router)
app.include_router(proxy.router)


@app.get("/api/health")
async def health():
    """健康检查。"""
    return {"status": "ok"}


# 静态文件托管（前端页面）
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
