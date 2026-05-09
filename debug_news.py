import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from datetime import datetime, timedelta, timezone
from alpaca.data.historical import NewsClient
from alpaca.data.requests import NewsRequest
from shared.config import cfg

client = NewsClient(cfg.alpaca_api_key, cfg.alpaca_secret_key)
start = datetime.now(timezone.utc) - timedelta(days=7)

req = NewsRequest(symbols="AAPL", start=start, limit=5)
response = client.get_news(req)

print(f"Tipo response: {type(response)}")

news_dict = dict(response)
print(f"Claves: {list(news_dict.keys())}")

data = news_dict.get("data", [])
print(f"Noticias en data: {len(data)}")

if data:
    article = data[0]
    print(f"Tipo articulo: {type(article)}")
    if isinstance(article, dict):
        print(f"Keys: {list(article.keys())}")
        print(f"Headline: {article.get('headline', article.get('title', '?'))[:60]}")
    elif hasattr(article, "headline"):
        print(f"Headline: {article.headline[:60]}")
        print(f"Symbols: {article.symbols}")
        print(f"Created: {article.created_at}")