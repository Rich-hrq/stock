from fastapi import APIRouter, HTTPException

from ..schemas import PredictRequest
from ..services.polymarket import fetch_polymarket_data


router = APIRouter(prefix="/api", tags=["predict"])


@router.post("/predict")
async def get_prediction(req: PredictRequest):
    result = fetch_polymarket_data(
        keywords=req.keywords, limit=req.limit, threshold=req.threshold
    )
    if result is None:
        raise HTTPException(status_code=502, detail="Polymarket API 请求失败")
    return result
