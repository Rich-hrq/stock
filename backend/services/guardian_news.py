"""
Guardian News Scraper
"""

from datetime import datetime
import httpx
from bs4 import BeautifulSoup
from ..config import HTTP_PROXY


async def scrape_guardian_news(url="https://www.theguardian.com/us"):
    """抓取新闻"""
    # 1.sending request(GET)
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    proxy = HTTP_PROXY if HTTP_PROXY else None

    try:
        async with httpx.AsyncClient(proxy=proxy, timeout=15) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()  # 如果状态码是 403/404/500，直接报错
            html_text = response.text
    except httpx.HTTPError as e:
        print(f"请求失败: {e}")
        return None

    # 2.parsing response
    soup = BeautifulSoup(html_text, "html.parser")  # stuctuing: text -> DOM tree
    news_items = []

    for article in soup.find_all("a", href=True):
        href = article.get("href")  # 提取<a>标签中href属性
        title = article.get_text(strip=True)  # 自动去掉空格、换行，让标题干净

        if not href:
            continue

        # 处理相对链接
        if href.startswith("/"):
            full_url = f"https://www.theguardian.com{href}"
        else:
            full_url = href

        # 标题过滤
        if not title or len(title) < 10 or len(title) > 200:
            continue

        # 排除链接
        # 网站功能页链接
        if any(
            x in href
            for x in [
                "/preference/",
                "/signin",
                "/subscribe",
                "/jobs",
                "/support",
                "#comments",
            ]
        ):
            continue

        if f"/{datetime.now().strftime('%Y')}/" in href:
            news_items.append({"title": title, "link": full_url})

    # 去重
    seen = set()
    unique_items = []
    for item in news_items:
        if item["link"] not in seen:
            seen.add(item["link"])
            unique_items.append(item)

    return unique_items
