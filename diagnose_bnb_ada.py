"""Diagnose why BNB/USDT and ADA/USDT produce unusable training data.

Runs each pipeline step individually and prints results at every stage.
"""

from decimal import Decimal

from src.data.binance_client import BinanceClient
from src.data.feature_engineer import FeatureEngineer

client = BinanceClient()
engineer = FeatureEngineer()


def diagnose(pair: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  DIAGNOSING: {pair}")
    print(f"{'=' * 60}")

    # --- Step 1: OHLCV ---
    print(f"\n--- Step 1: OHLCV (limit=1000) ---")
    try:
        ohlcv = client.get_ohlcv(pair, "1h", limit=1000)
        print(f"  Row count: {len(ohlcv)}")
        print(f"  First timestamp: {ohlcv['timestamp'].iloc[0]}")
        print(f"  Last timestamp:  {ohlcv['timestamp'].iloc[-1]}")
        print(f"  Date range: {ohlcv['timestamp'].iloc[0]} to {ohlcv['timestamp'].iloc[-1]}")
    except Exception as exc:
        print(f"  FAILED: {type(exc).__name__}: {exc}")
        print("  VERDICT: OHLCV fetch failed — data pipeline cannot proceed")
        return

    # --- Step 2: Funding rate + Open interest ---
    print(f"\n--- Step 2: Funding Rate & Open Interest ---")
    try:
        fr = client.get_funding_rate(pair)
        print(f"  Funding rate: {fr}")
    except Exception as exc:
        print(f"  Funding rate FAILED: {type(exc).__name__}: {exc}")
        fr = {"funding_rate": Decimal("0")}

    try:
        oi = client.get_open_interest(pair)
        print(f"  Open interest: {oi}")
    except Exception as exc:
        print(f"  Open interest FAILED: {type(exc).__name__}: {exc}")
        oi = {"open_interest": Decimal("0")}

    # --- Step 3: Feature engineering ---
    print(f"\n--- Step 3: Feature Engineering ---")
    try:
        fr_float = float(fr.get("funding_rate", Decimal("0")))
        oi_float = float(oi.get("open_interest", Decimal("0")))
        features = engineer.compute_features(
            ohlcv,
            funding_rate=fr_float,
            open_interest=oi_float,
            fear_greed=50,
        )
        print(f"  Row count after NaN drop: {len(features)}")
        print(f"  Columns: {list(features.columns)}")
    except Exception as exc:
        print(f"  FAILED: {type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()
        print("  VERDICT: Feature engineering failed — cannot train")
        return

    # --- Step 4: Class balance of target_vol_regime ---
    print(f"\n--- Step 4: target_vol_regime Class Balance ---")
    if "target_vol_regime" in features.columns:
        zeros = int((features["target_vol_regime"] == 0).sum())
        ones = int((features["target_vol_regime"] == 1).sum())
        total = zeros + ones
        if total > 0:
            zero_pct = zeros / total * 100
            one_pct = ones / total * 100
            print(f"  Class 0 (low vol): {zeros} ({zero_pct:.1f}%)")
            print(f"  Class 1 (high vol): {ones} ({one_pct:.1f}%)")
            if zero_pct > 90 or one_pct > 90:
                print(f"  WARNING: Class imbalance > 90% — classifier will not learn")
            elif zero_pct > 80 or one_pct > 80:
                print(f"  NOTE: Moderate imbalance (>{'80' if zero_pct > 80 else ''}/{'20' if one_pct > 80 else ''} split)")
            else:
                print(f"  OK: Reasonably balanced")
        else:
            print(f"  WARNING: No target rows available")
    else:
        print(f"  WARNING: target_vol_regime column not found in features")

    # --- Final verdict ---
    print(f"\n--- FINAL VERDICT for {pair} ---")
    row_count = len(features) if "features" in dir() else 0
    if row_count < 500:
        print(f"  FAIL: Row count {row_count} < 500 — insufficient data for training")
        if row_count < 50:
            print(f"  Likely cause: NaN drop removed most rows")
        else:
            print(f"  Likely cause: partial NaN drop or insufficient OHLCV data")
    elif row_count < 1000:
        print(f"  MARGINAL: Row count {row_count} — 500+ is training-capable but not ideal")
    else:
        print(f"  PASS: Row count {row_count} — sufficient data for training")


diagnose("BNB/USDT")
diagnose("ADA/USDT")
