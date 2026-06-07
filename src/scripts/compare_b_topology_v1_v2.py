"""Compare v1 (2.4y, 2026-05-24) vs v2 (deep, 2026-05-26) B-topology CSVs.

Produces:
  - signal counts (total, per-direction, per-symbol)
  - direction baseline mean + bootstrap CI
  - per rule_id  mean + bootstrap CI
  - R4 spotlight buckets:
      top direction (n, mean, CI)
      F8-cn-no-boost = bottom+weakness (n, mean, CI)
      top+higher_supporting (n, mean, CI)
      top+higher_opposing  (n, mean, CI)
      bottom+higher_opposing (n, mean, CI)
  - any NEW stable bucket (n>=30, mean CI does not cross zero)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

N_BOOTSTRAP = 5000
RNG_SEED = 42


def boot_ci(x, alpha=0.05):
    x = np.asarray(x, dtype=float)
    if len(x) == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(RNG_SEED)
    m = rng.choice(x, size=(N_BOOTSTRAP, len(x)), replace=True).mean(axis=1)
    lo, hi = np.quantile(m, [alpha / 2, 1 - alpha / 2])
    return float(lo), float(hi)


def stat_row(sub):
    if sub.empty:
        return None
    rets = sub["signed_return"].to_numpy()
    lo, hi = boot_ci(rets)
    return {
        "n": int(len(sub)),
        "mean_pct": float(rets.mean() * 100),
        "hit_pct": float(sub["hit"].mean() * 100),
        "ci_lo_pct": lo * 100,
        "ci_hi_pct": hi * 100,
        "ci_crosses_zero": (lo < 0) and (hi > 0),
    }


def fmt(d):
    if d is None:
        return "(empty)"
    cz = "[CROSSES ZERO]" if d["ci_crosses_zero"] else ""
    return (f"n={d['n']:>4d}  hit={d['hit_pct']:5.1f}%  mean={d['mean_pct']:+6.2f}%  "
            f"CI [{d['ci_lo_pct']:+6.2f}%, {d['ci_hi_pct']:+6.2f}%]  {cz}")


def load(path: Path, horizon=20) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df[df["horizon"] == horizon].copy()
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def spotlight(df, label, mask):
    sub = df[mask]
    print(f"  {label:55s} {fmt(stat_row(sub))}")
    return stat_row(sub)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--v1", type=Path, required=True)
    p.add_argument("--v2", type=Path, required=True)
    p.add_argument("--horizon", type=int, default=20)
    args = p.parse_args()

    v1 = load(args.v1, args.horizon)
    v2 = load(args.v2, args.horizon)

    print("=" * 80)
    print(f"V1 (2026-05-24): n_signals={v1['symbol'].count()//1} rows  "
          f"unique_signals={len(v1)}  date range "
          f"{v1['date'].min().date()} → {v1['date'].max().date()}")
    print(f"V2 (2026-05-26): unique_signals={len(v2)}  date range "
          f"{v2['date'].min().date()} → {v2['date'].max().date()}")
    print(f"  growth factor: {len(v2)/max(len(v1),1):.2f}x")
    print("=" * 80)

    # Direction baseline
    print("\n--- DIRECTION BASELINE (h=20) ---")
    for direction in ("bottom", "top"):
        print(f"\n{direction.upper()}:")
        print("  v1:", fmt(stat_row(v1[v1["direction"] == direction])))
        print("  v2:", fmt(stat_row(v2[v2["direction"] == direction])))

    # Per-symbol counts
    print("\n--- PER-SYMBOL SIGNAL COUNTS (h=20) ---")
    s1 = v1.groupby("symbol").size().rename("v1_n")
    s2 = v2.groupby("symbol").size().rename("v2_n")
    merged = pd.concat([s1, s2], axis=1).fillna(0).astype(int)
    merged["growth"] = (merged["v2_n"] / merged["v1_n"].clip(lower=1)).round(2)
    print(merged.sort_values("v2_n", ascending=False).to_string())

    # Per rule_id
    print("\n--- PER rule_id (h=20) ---")
    print("v1:")
    for rule, sub in v1.groupby("rule_id"):
        print(f"  {str(rule):30s} {fmt(stat_row(sub))}")
    print("v2:")
    for rule, sub in v2.groupby("rule_id"):
        print(f"  {str(rule):30s} {fmt(stat_row(sub))}")

    # R4 spotlight buckets
    print("\n--- R4 SPOTLIGHT BUCKETS (h=20) ---")
    print("\n[v1]")
    spotlight(v1, "top direction",
              v1["direction"] == "top")
    spotlight(v1, "F8-cn-no-boost (bottom + weakness)",
              (v1["direction"] == "bottom") & (v1["subtype"] == "weakness"))
    spotlight(v1, "top + higher_supporting",
              (v1["direction"] == "top") & (v1["higher_relation"] == "supporting"))
    spotlight(v1, "top + higher_opposing",
              (v1["direction"] == "top") & (v1["higher_relation"] == "opposing"))
    spotlight(v1, "bottom + higher_opposing",
              (v1["direction"] == "bottom") & (v1["higher_relation"] == "opposing"))

    print("\n[v2]")
    spotlight(v2, "top direction",
              v2["direction"] == "top")
    spotlight(v2, "F8-cn-no-boost (bottom + weakness)",
              (v2["direction"] == "bottom") & (v2["subtype"] == "weakness"))
    spotlight(v2, "top + higher_supporting",
              (v2["direction"] == "top") & (v2["higher_relation"] == "supporting"))
    spotlight(v2, "top + higher_opposing",
              (v2["direction"] == "top") & (v2["higher_relation"] == "opposing"))
    spotlight(v2, "bottom + higher_opposing",
              (v2["direction"] == "bottom") & (v2["higher_relation"] == "opposing"))

    # Hunt for NEW stable buckets in v2 at n>=30 with CI not crossing zero
    print("\n--- HUNT: V2 stable buckets (n>=30, CI doesn't cross zero) ---")
    groupings = [
        (["direction"], "direction"),
        (["direction", "subtype"], "direction × subtype"),
        (["direction", "higher_relation"], "direction × higher_relation"),
        (["direction", "lower_relation"], "direction × lower_relation"),
        (["direction", "lower_relation", "higher_relation"], "direction × lower × higher"),
        (["direction", "subtype", "higher_relation"], "direction × subtype × higher"),
        (["rule_id"], "rule_id"),
        (["direction", "rule_id"], "direction × rule_id"),
    ]
    candidates = []
    for cols, title in groupings:
        for key, sub in v2.groupby(cols):
            if len(sub) < 30:
                continue
            s = stat_row(sub)
            if s is None: continue
            if s["ci_crosses_zero"]:
                continue
            key_str = key if isinstance(key, str) else " / ".join(map(str, key))
            candidates.append((title, key_str, s))
    if not candidates:
        print("  (no qualifying buckets)")
    else:
        # sort by absolute mean descending
        candidates.sort(key=lambda r: -abs(r[2]["mean_pct"]))
        for title, k, s in candidates:
            sign = "+" if s["mean_pct"] > 0 else "-"
            print(f"  [{title}] {k:55s} {fmt(s)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
