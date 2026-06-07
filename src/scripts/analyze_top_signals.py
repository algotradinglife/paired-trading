"""Diagnostic: drill into top-signal failure modes across snapshots.

Output: hit-rate breakdown for top signals only, sliced by every feature we
could realistically gate on (subtype, level, conf band, container_type,
is_continuous_gap, amplitude.decay_ratio buckets).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from scripts.backtest_signals import (
    CONF_BANDS, FORWARD_WINDOWS, conf_band, run_pipeline_and_eval,
)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

SNAPSHOTS = ["spy_daily.json", "qqq_daily.json", "nvda_daily.json", "gld_daily.json"]


def main() -> int:
    all_rows = []
    for sn in SNAPSHOTS:
        path = DATA_DIR / "raw" / sn
        if not path.exists():
            continue
        rows = run_pipeline_and_eval(path, min_conf=0.3, horizons=FORWARD_WINDOWS)
        for r in rows:
            sig = r.signal
            if sig.direction != "top":
                continue
            all_rows.append({
                "snapshot": sn,
                "subtype": sig.subtype,
                "level": sig.level,
                "container_type": sig.container_type,
                "conf_band": conf_band(sig.confidence),
                "confidence": sig.confidence,
                "is_continuous_gap": sig.is_continuous_gap,
                "decay_ratio": sig.amplitude_side.decay_ratio,
                "hit_5":  r.hits[5],
                "hit_10": r.hits[10],
                "hit_20": r.hits[20],
                "sret_5":  r.signed_returns[5],
                "sret_10": r.signed_returns[10],
                "sret_20": r.signed_returns[20],
                "mfe_20": r.mfes[20],
                "mae_20": r.maes[20],
            })

    df = pd.DataFrame(all_rows)
    print(f"Total top signals: {len(df)}")
    print(f"Baseline:  h5={df['hit_5'].mean():.1%}  h10={df['hit_10'].mean():.1%}  h20={df['hit_20'].mean():.1%}  avg_sret_20={df['sret_20'].mean()*100:+.2f}%")

    def show(col: str, label: str | None = None):
        label = label or col
        g = df.groupby(col, dropna=False)
        out = pd.DataFrame({
            "n": g.size(),
            "h5":  g["hit_5"].mean(),
            "h10": g["hit_10"].mean(),
            "h20": g["hit_20"].mean(),
            "sret_20%": g["sret_20"].mean() * 100,
            "mfe20%": g["mfe_20"].mean() * 100,
            "mae20%": g["mae_20"].mean() * 100,
        }).reset_index()
        out["mfe/mae"] = out["mfe20%"] / out["mae20%"]
        for c in ("h5", "h10", "h20"):
            out[c] = (out[c] * 100).round(1).astype(str) + "%"
        out["sret_20%"] = out["sret_20%"].round(2).astype(str) + "%"
        out["mfe20%"] = out["mfe20%"].round(2).astype(str) + "%"
        out["mae20%"] = out["mae20%"].round(2).astype(str) + "%"
        out["mfe/mae"] = out["mfe/mae"].round(2)
        print(f"\n=== Top signals by {label} ===")
        print(out.to_string(index=False))

    show("subtype")
    show("level")
    show("container_type")
    show("conf_band")
    show("is_continuous_gap")

    # 2-way: subtype × level
    print("\n=== Top signals by subtype × level ===")
    g = df.groupby(["subtype", "level"], dropna=False)
    out = pd.DataFrame({
        "n": g.size(),
        "h10": g["hit_10"].mean(),
        "h20": g["hit_20"].mean(),
        "sret_20%": g["sret_20"].mean() * 100,
    }).reset_index()
    for c in ("h10", "h20"):
        out[c] = (out[c] * 100).round(1).astype(str) + "%"
    out["sret_20%"] = out["sret_20%"].round(2).astype(str) + "%"
    print(out.to_string(index=False))

    # 2-way: subtype × conf_band
    print("\n=== Top signals by subtype × conf_band ===")
    g = df.groupby(["subtype", "conf_band"], dropna=False)
    out = pd.DataFrame({
        "n": g.size(),
        "h10": g["hit_10"].mean(),
        "h20": g["hit_20"].mean(),
        "sret_20%": g["sret_20"].mean() * 100,
    }).reset_index()
    for c in ("h10", "h20"):
        out[c] = (out[c] * 100).round(1).astype(str) + "%"
    out["sret_20%"] = out["sret_20%"].round(2).astype(str) + "%"
    print(out.to_string(index=False))

    # confidence quartiles
    df["conf_quartile"] = pd.qcut(df["confidence"], 4, labels=["Q1_low", "Q2", "Q3", "Q4_high"])
    show("conf_quartile")

    # decay_ratio buckets
    df["decay_bucket"] = pd.cut(df["decay_ratio"], [0, 0.5, 0.75, 0.9, 1.0, 100], labels=["<0.5", "0.5-0.75", "0.75-0.9", "0.9-1.0", ">1.0"])
    show("decay_bucket")

    return 0


if __name__ == "__main__":
    sys.exit(main())
