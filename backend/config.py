"""项目配置，通过环境变量管理敏感信息。"""

import os
from pathlib import Path

# ---- 基础路径 ----
PROJECT_ROOT = Path(__file__).parent.parent  # stock_website/
BACKEND_DIR = Path(__file__).parent  # stock_website/backend/
KNOWLEDGE_DIR = BACKEND_DIR / "knowledge"
CHROMA_DB_DIR = KNOWLEDGE_DIR / "chroma_db"
STATIC_DIR = PROJECT_ROOT / "frontend"
PDF_PATH = PROJECT_ROOT.parent / "海龟交易法则.pdf"

# ---- Anthropic API 配置 ----
# 支持多种环境变量名：ANTHROPIC_API_KEY / CLAUDE_KEY / ANTHROPIC_AUTH_TOKEN
ANTHROPIC_API_KEY = os.environ.get(
    "ANTHROPIC_API_KEY",
    os.environ.get("CLAUDE_KEY", os.environ.get("ANTHROPIC_AUTH_TOKEN", "")),
)
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# ---- 美股指数配置 ----
US_INDEXES: dict[str, str] = {
    "标普500": "^GSPC",
    "纳斯达克100": "^NDX",
    "纳斯达克综合指数": "^IXIC",
    "道琼斯工业指数": "^DJI",
}

# ---- 网络代理 ----
HTTP_PROXY = os.environ.get("all_proxy", "http://127.0.0.1:7897")

# ---- 技术指标参数 ----
BOLLINGER_PERIOD = 20
BOLLINGER_STD = 2.0
ATR_PERIOD = 20
DONCHIAN_ENTRY = 20  # 唐奇安通道入场周期（日）
DONCHIAN_STOP = 55  # 唐奇安通道止损周期（日）

# ---- RAG 参数 ----
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
TOP_K_RETRIEVAL = 5

# ---- MySQL 配置 ----
MYSQL_HOST = os.environ.get("MYSQL_HOST", "")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "stock")

# ---- JWT 配置 ----
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 7

# ---- 汇率 API ----
EXCHANGE_RATE_URL = "https://open.er-api.com/v6/latest/USD"

# ---- 数据缓存 ----
MARKET_DATA_CACHE_DIR = BACKEND_DIR / "cache" / "market_data"
MARKET_DATA_CACHE_ENABLED = True
MARKET_DATA_CACHE_MAX_AGE_DAYS = 7
