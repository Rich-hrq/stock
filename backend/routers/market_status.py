"""市场状态 API 路由：返回美股当前交易时段及双时区时间信息。"""

from fastapi import APIRouter

from ..services.market_status import get_market_status

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/status")
async def market_status():
    """获取美股市场当前交易状态。

    返回当前时段（盘前/盘中/盘后/休市）、
    美东时间与北京时间的当前时间及下一次开盘/收盘时间。
    """
    return get_market_status()
