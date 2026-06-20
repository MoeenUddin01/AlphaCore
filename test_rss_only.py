"""Quick smoke test: run DataPipeline and print RSS news per pair."""

from src.data.data_pipeline import DataPipeline

pipeline = DataPipeline()
result = pipeline.run()

for pair, data in result.items():
    news = data.get("news", [])
    print(f"\n=== {pair} === headlines: {len(news)}")
    for i, article in enumerate(news[:2], 1):
        print(f"  {i}. {article.get('title', 'N/A')} — {article.get('source', 'N/A')}")
