"""SQLAlchemy ORM 模型定义。"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有模型的基类。"""
    pass


class User(Base):
    """用户表。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(20), unique=True, comment="用户名")
    password_hash: Mapped[str] = mapped_column(String(128), comment="bcrypt 加密密码")
    created_at: Mapped[datetime] = mapped_column(default=func.now(), comment="注册时间")


class Transaction(Base):
    """交易记录表。"""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), comment="所属用户")
    symbol: Mapped[str] = mapped_column(String(20), comment="指数代码（如 ^GSPC）")
    direction: Mapped[str] = mapped_column(String(4), comment="buy 或 sell")
    trade_date: Mapped[date] = mapped_column(comment="交易日期")
    amount_cny: Mapped[Decimal] = mapped_column(Numeric(12, 2), comment="人民币金额")
    close_price_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), comment="当日收盘价（美元）"
    )
    exchange_rate: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), comment="当日 USD/CNY 汇率"
    )
    usd_equivalent: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), comment="美元等值（amount_cny / rate）"
    )
    shares: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), comment="持有份额（usd_equivalent / close_price）"
    )
    created_at: Mapped[datetime] = mapped_column(default=func.now(), comment="记录创建时间")
