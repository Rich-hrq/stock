import httpx
from ..config import HTTP_PROXY


async def fetch_polymarket_data(
    keywords: list[str],
    limit: int = 500,
    threshold: int = 100000,
) -> list[dict] | None:
    url = "https://gamma-api.polymarket.com/events"
    params = {
        "limit": limit,
        "active": "true",
        "closed": "false",
        "volume_min": threshold,
    }
    proxy = HTTP_PROXY if HTTP_PROXY else None

    try:
        async with httpx.AsyncClient(proxy=proxy, timeout=5) as client:
            response = await client.get(url, params=params)
        response.raise_for_status()
    except httpx.HTTPError as e:
        print("Request failed：", e)
        return

    events = response.json()  # list[dict]
    extracted_events = []

    for event in events:
        title = event.get("title", "")
        meta = event.get("eventMetadata", {}).get("context_description", "")
        context = [title, event.get("description", ""), meta]

        if check_relevant(context, keywords):
            extracted = extract(event)
            extracted_events.append(extracted)
    return extracted_events


def check_relevant(context: list[str], keywords: list[str]) -> bool:
    """
    检测 context 中是否包含 keywords
    """
    for k in keywords:
        for c in context:
            if k.lower() not in c.lower():
                continue
            return True
    return False


def extract(event: dict) -> dict:
    title = event.get("title", "")
    desc = event.get("description", "")

    markets = []
    for m in event.get("markets", []):
        markets.append(
            {
                "question": m.get("question", ""),
                "endDate": m.get("endDate", ""),
                "description": m.get("description", ""),
                "outcomePrices": m.get("outcomePrices", ""),
                "volume": m.get("volume", 0),
            }
        )

    meta = event.get("eventMetadata", {})
    meta_info = {
        "context_description": meta.get("context_description", ""),
        "context_updated_at": meta.get("context_updated_at", ""),
    }

    return {"title": title, "description": desc, "markets": markets, "meta": meta_info}
