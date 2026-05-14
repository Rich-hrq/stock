"""Guardian 页面代理 — 获取 HTML 并注入 <base> 标签使浏览器能加载子资源。"""

from urllib.parse import urlparse
import requests
from ..config import HTTP_PROXY

ALLOWED_DOMAIN = "www.theguardian.com"
BASE_HREF = f'<base href="https://{ALLOWED_DOMAIN}">'


def fetch_page(url: str, timeout: int = 15) -> str:
    """获取 Guardian 页面 HTML。

    1. 域名白名单校验（仅放行 www.theguardian.com）
    2. 通过代理请求 Guardian 页面
    3. 注入 <base> 标签使浏览器正确解析相对路径资源
    4. 返回修改后的 HTML
    """
    # 域名白名单校验
    parsed = urlparse(url)
    if parsed.netloc != ALLOWED_DOMAIN:
        raise ValueError(f"不允许的域名: {parsed.netloc}，仅支持 {ALLOWED_DOMAIN}")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
    }
    proxies = {"http": HTTP_PROXY, "https": HTTP_PROXY}

    try:
        response = requests.get(url, headers=headers, proxies=proxies, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"请求 Guardian 失败: {e}") from e

    html = response.text

    # 注入 <base> 标签到 <head> 之后，使浏览器自动用 Guardian 域名解析相对路径
    if "<base " in html:
        # 页面已有 <base>，替换之
        import re
        html = re.sub(r'<base[^>]*>', BASE_HREF, html, count=1)
    else:
        html = html.replace("<head>", f"<head>\n    {BASE_HREF}", 1)

    return html
