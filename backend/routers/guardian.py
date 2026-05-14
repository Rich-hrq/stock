from fastapi import APIRouter, HTTPException
from ..services.guardian_news import scrape_guardian_news as fetch_news

router = APIRouter(prefix="/api", tags=["guardian_news"])


@router.post("/guardian_news")
async def get_news():
    result = fetch_news()
    if result is None:
        raise HTTPException(status_code=502, detail="新闻爬取失败")
    return result
