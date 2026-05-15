"""数据库引擎与会话管理，使用 SQLAlchemy 2.0 async + aiomysql。"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE
from .models import Base


def _build_url() -> str:
    """构建 MySQL 异步连接 URL。"""
    return (
        f"mysql+aiomysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
        f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}?charset=utf8mb4"
    )


engine = create_async_engine(
    _build_url(),
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    """启动时自动创建所有表（如已存在则跳过）。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖注入：提供数据库会话。"""
    async with async_session() as session:
        yield session
