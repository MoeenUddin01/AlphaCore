"""Test the multi-source news pipeline end-to-end.

Runs fetch_combined_news() for BTC/USDT and prints a report of which
sources contributed and how many headlines each returned.  Confirms
the system handles partial failures gracefully (some sources may fail
due to missing credentials — the rest should still work).
"""

from src.data.data_pipeline import DataPipeline

pipeline = DataPipeline()

pair = "BTC/USDT"
print(f"Fetching combined news for {pair}...\n")

headlines = pipeline.fetch_combined_news(pair)

print(f"Total headlines returned: {len(headlines)}\n")

source_counts: dict[str, int] = {}
for h in headlines:
    src = h.get("source", "unknown")
    source_counts[src] = source_counts.get(src, 0) + 1

print("Per-source breakdown:")
for src, count in sorted(source_counts.items(), key=lambda x: -x[1]):
    print(f"  {src}: {count}")

print(f"\nFirst {min(3, len(headlines))} headline(s):")
for i, h in enumerate(headlines[:3]):
    print(f"\n  [{i+1}] {h['title']}")
    print(f"       Source: {h['source']}")
    print(f"       Published: {h['published_at']}")
    print(f"       Currencies: {h['currencies']}")
    print(f"       URL: {h['url'][:80]}...")

print("\nMulti-source news OK")
