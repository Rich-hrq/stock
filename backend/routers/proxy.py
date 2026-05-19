"""Guardian 页面代理 API。"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse

from ..services.proxy import fetch_page

router = APIRouter(prefix="/api", tags=["proxy"])


@router.get("/proxy")
async def proxy(url: str = Query(..., description="Guardian 文章 URL")):
    """代理一个 Guardian 页面，返回注入 <base> 标签后的完整 HTML。

    仅允许 www.theguardian.com 域名的链接，其他域名返回 403。
    """
    if not url:
        raise HTTPException(status_code=400, detail="缺少 url 参数")

    try:
        html = await fetch_page(url)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return HTMLResponse(content=html, status_code=200)
