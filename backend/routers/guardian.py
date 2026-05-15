from datetime import datetime

from fastapi import APIRouter, HTTPException

from ..schemas import NewsSummaryRequest, NewsSummaryResponse
from ..services.guardian_news import scrape_guardian_news as fetch_news
from ..services.news_summary import generate_summary

router = APIRouter(prefix="/api", tags=["guardian_news"])


@router.post("/guardian_news")
async def get_news():
    result = fetch_news()
    if result is None:
        raise HTTPException(status_code=502, detail="新闻爬取失败")
    return result


@router.post("/news/summary", response_model=NewsSummaryResponse)
async def summarize_news(req: NewsSummaryRequest):
    if not req.headlines:
        raise HTTPException(status_code=400, detail="无新闻标题可供摘要")
    summary = generate_summary(req.headlines)
    return NewsSummaryResponse(
        summary=summary,
        generated_at=datetime.now().isoformat(),
    )
