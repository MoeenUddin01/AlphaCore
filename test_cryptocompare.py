"""Test the CryptoCompareClient end-to-end.

Prints raw response top-level keys on first call, then shows
all returned articles with full dict contents.
"""

from src.data.cryptocompare_client import CryptoCompareClient

client = CryptoCompareClient()
news = client.get_news_for_pair("BTC/USDT", limit=5)

print(f"\nNews items returned: {len(news)}\n")

for i, article in enumerate(news, 1):
    print(f"--- Article {i} ---")
    for key, value in article.items():
        print(f"  {key}: {value}")
    print()

if not news:
    print("No articles returned (likely need a valid API key).")
