from fastapi import APIRouter, HTTPException

from ..schemas import PredictRequest, PredictSearchRequest
from ..services.polymarket import fetch_polymarket_data, search_polymarket_events


router = APIRouter(prefix="/api", tags=["predict"])


@router.post("/predict")
async def get_prediction(req: PredictRequest):
    result = await fetch_polymarket_data(
        keywords=req.keywords, limit=req.limit, threshold=req.threshold
    )
    if result is None:
        raise HTTPException(status_code=502, detail="Polymarket API 请求失败")
    return result


@router.post("/predict/search")
async def search_prediction(req: PredictSearchRequest):
    result = await search_polymarket_events(
        query=req.query, limit_per_type=req.limit_per_type, threshold=req.threshold
    )
    if result is None:
        raise HTTPException(status_code=502, detail="Polymarket 搜索 API 请求失败")
    return result
