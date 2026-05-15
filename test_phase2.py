#!/usr/bin/env python3
"""Temporary test script for Phase 2 data pipeline."""

from src.data.data_pipeline import DataPipeline

pipeline = DataPipeline()
result = pipeline.run()

for pair, data in result.items():
    df = data["ohlcv_features"]
    print(f"\n=== {pair} ===")
    print(f"  OHLCV features shape:   {df.shape}")
    print(f"  Current price:          {data['current_price']}")
    print(f"  News headlines:         {len(data['news'])}")
    fng = data["fear_greed"]
    print(f"  Fear & Greed:           value={fng.get('value')}, classification={fng.get('classification')}")

print("\nPhase 2 data pipeline OK")
