"""Systematic pattern mining over the signal-level CSV.

Enumerates 1-, 2-, and 3-dimensional bucket combinations across:
  direction, subtype, lower_relation, lower_cycle, higher_relation, higher_cycle

For each bucket with n >= MIN_N at horizon h=20, computes:
  - n
  - hit_rate                  binary win/loss rate
  - mean / median signed_ret
  - bootstrap 95% CI on mean  (B=1000 resamples)
  - HHI                       symbol concentration ([0,1], lower = more diverse)
  - p_hit                     binomial two-sided p-value vs null=0.5
  - p_mean                    one-sample t-test p-value vs null=0
  - p_hit_bonferroni          Bonferroni-corrected (k = # tested buckets)
  - p_mean_bonferroni
  - p_hit_fdr                 Benjamini-Hochberg FDR-adjusted
  - p_mean_fdr
  - drop_top2_mean            mean after removing 2 largest returns (outlier robustness)
  - winsor_mean               mean after winsorizing top/bottom 5%

Outputs:
  data/review/mined_patterns_h20.csv       all buckets, sortable
  data/review/mined_patterns_h20_top.md    markdown summary of top candidates
"""

from __future__ import annotations

import os
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from scipy import stats

DIMENSIONS = [
    "direction",
    "subtype",
    "lower_relation",
    "lower_cycle",
    "higher_relation",
    "higher_cycle",
]
MIN_N = 10
HORIZON = 20
BOOTSTRAP_B = 1000
def _default_review_dir() -> Path:
    """Default review dir; honors DERIVED_ROOT env var, falls back to src/data/review."""
    derived = os.environ.get("DERIVED_ROOT")
    if derived:
        return Path(derived) / "paired-trading" / "src-data-review"
    return Path(__file__).resolve().parents[1] / "data" / "review"


OUT_DIR = _default_review_dir()
CSV_IN = OUT_DIR / "signals_2026-05-23.csv"


def hhi(symbols: pd.Series) -> float:
    """Herfindahl-Hirschman Index of symbol concentration. 0 = uniform, 1 = one symbol."""
    counts = symbols.value_counts(normalize=True)
    return float((counts ** 2).sum())


def bootstrap_mean_ci(values: np.ndarray, ci: float = 0.95, B: int = BOOTSTRAP_B,
                     seed: int = 42) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    n = len(values)
    if n == 0:
        return (float("nan"), float("nan"))
    samples = rng.choice(values, size=(B, n), replace=True).mean(axis=1)
    lo = float(np.percentile(samples, (1 - ci) / 2 * 100))
    hi = float(np.percentile(samples, (1 + ci) / 2 * 100))
    return lo, hi


def drop_top_n_mean(values: np.ndarray, n: int = 2) -> float:
    if len(values) <= n:
        return float("nan")
    return float(np.sort(values)[:-n].mean())


def winsorize_mean(values: np.ndarray, alpha: float = 0.05) -> float:
    if len(values) < 4:
        return float("nan")
    lo, hi = np.percentile(values, [alpha * 100, (1 - alpha) * 100])
    return float(np.clip(values, lo, hi).mean())


def fdr_bh(pvalues: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg FDR correction. Returns adjusted p-values."""
    pvalues = np.asarray(pvalues, dtype=float)
    n = len(pvalues)
    if n == 0:
        return pvalues
    order = np.argsort(pvalues)
    ranked = pvalues[order]
    adj = ranked * n / (np.arange(n) + 1)
    # Enforce monotonicity from the back
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    adj = np.clip(adj, 0, 1)
    out = np.empty(n, dtype=float)
    out[order] = adj
    return out


def explore_buckets(df: pd.DataFrame, dims: list[str]) -> list[dict]:
    """Group df by `dims`, compute per-bucket stats."""
    out = []
    grouped = df.groupby(dims, dropna=False)
    for keys, sub in grouped:
        if len(sub) < MIN_N:
            continue
        values = sub["signed_return"].to_numpy(dtype=float)
        hits = sub["hit"].to_numpy(dtype=bool)
        n = len(sub)
        hit_rate = float(hits.mean())
        mean_ret = float(values.mean())
        median_ret = float(np.median(values))
        ci_lo, ci_hi = bootstrap_mean_ci(values)
        symbol_hhi = hhi(sub["symbol"])

        # Two-sided binomial test for hit_rate vs 0.5
        binom = stats.binomtest(int(hits.sum()), n, p=0.5, alternative="two-sided")
        p_hit = binom.pvalue

        # One-sample t-test of mean vs 0
        if np.allclose(values.std(), 0.0):
            p_mean = 1.0
        else:
            tres = stats.ttest_1samp(values, 0.0)
            p_mean = float(tres.pvalue)

        bucket = {
            "dims": "×".join(dims),
            "n_dims": len(dims),
            "n": n,
            "hit_rate": hit_rate,
            "mean_ret": mean_ret,
            "median_ret": median_ret,
            "ci95_lo": ci_lo,
            "ci95_hi": ci_hi,
            "drop_top2_mean": drop_top_n_mean(values),
            "winsor5pct_mean": winsorize_mean(values),
            "hhi": symbol_hhi,
            "p_hit": p_hit,
            "p_mean": p_mean,
        }
        # Add the bucket key columns
        if not isinstance(keys, tuple):
            keys = (keys,)
        for d, k in zip(dims, keys):
            bucket[d] = k
        out.append(bucket)
    return out


def mine(df_horizon: pd.DataFrame, max_dim: int = 3) -> pd.DataFrame:
    all_buckets: list[dict] = []
    for k in range(1, max_dim + 1):
        for combo in combinations(DIMENSIONS, k):
            all_buckets.extend(explore_buckets(df_horizon, list(combo)))

    df_out = pd.DataFrame(all_buckets)
    if df_out.empty:
        return df_out

    # Correct p-values across the family
    df_out["p_hit_bonferroni"] = np.clip(df_out["p_hit"] * len(df_out), 0, 1)
    df_out["p_mean_bonferroni"] = np.clip(df_out["p_mean"] * len(df_out), 0, 1)
    df_out["p_hit_fdr"] = fdr_bh(df_out["p_hit"].to_numpy())
    df_out["p_mean_fdr"] = fdr_bh(df_out["p_mean"].to_numpy())

    # Composite score: prefer high |hit_rate - 0.5| AND positive mean AND low HHI AND robust
    # Score in [0, 1]: more = stronger candidate
    df_out["abs_hit_dev"] = (df_out["hit_rate"] - 0.5).abs()
    df_out["score"] = (
        df_out["abs_hit_dev"]
        * (1 - df_out["p_hit_fdr"])
        * (1 - df_out["hhi"])
        * df_out["n"].clip(upper=50) / 50
    )
    return df_out.sort_values("score", ascending=False).reset_index(drop=True)


def write_markdown_summary(df: pd.DataFrame, top_n: int = 25, out_path: Path = None):
    if out_path is None:
        out_path = OUT_DIR / "mined_patterns_h20_top.md"
    lines = ["# Mined Patterns — h=20 (top {} by score)\n".format(top_n)]
    lines.append("Source: `data/review/signals_2026-05-23.csv` (266 signals × 1 horizon).")
    lines.append(f"Tested {len(df)} buckets (n ≥ {MIN_N}). Bonferroni & FDR computed across all.\n")
    lines.append("**Score** = |hit_rate-0.5| × (1−FDR p_hit) × (1−HHI) × min(n,50)/50 — higher is stronger.\n")
    lines.append("| rank | dims & values | n | hit | mean | median | CI95 | drop_top2 | winsor | HHI | p_hit(FDR) | p_mean(FDR) | score |")
    lines.append("|-----:|---------------|--:|----:|-----:|-------:|------|----------:|-------:|----:|-----------:|------------:|------:|")
    for i, r in df.head(top_n).iterrows():
        dim_values = []
        for d in DIMENSIONS:
            v = r.get(d)
            if pd.notna(v) and v != "n/a":
                dim_values.append(f"{d}={v}")
        dim_str = " · ".join(dim_values)
        lines.append(
            f"| {i+1} | {dim_str} | {int(r['n'])} | "
            f"{r['hit_rate']*100:.1f}% | {r['mean_ret']*100:+.2f}% | {r['median_ret']*100:+.2f}% | "
            f"[{r['ci95_lo']*100:+.2f}%, {r['ci95_hi']*100:+.2f}%] | "
            f"{r['drop_top2_mean']*100:+.2f}% | {r['winsor5pct_mean']*100:+.2f}% | "
            f"{r['hhi']:.2f} | {r['p_hit_fdr']:.4f} | {r['p_mean_fdr']:.4f} | {r['score']:.3f} |"
        )
    out_path.write_text("\n".join(lines) + "\n")
    print(f"Top-N markdown → {out_path}")


def main() -> int:
    if not CSV_IN.exists():
        print(f"ERROR: input CSV not found: {CSV_IN}", file=sys.stderr)
        return 2
    raw = pd.read_csv(CSV_IN)
    h = raw[raw["horizon"] == HORIZON].copy()
    print(f"Loaded {len(raw)} rows; using {len(h)} for horizon={HORIZON}")
    mined = mine(h, max_dim=3)
    if mined.empty:
        print("No buckets with n >= MIN_N found.")
        return 0

    out_csv = OUT_DIR / "mined_patterns_h20.csv"
    mined.to_csv(out_csv, index=False)
    print(f"All buckets ({len(mined)}) → {out_csv}")
    write_markdown_summary(mined, top_n=25)

    # Also write "Codex-style" verdict groups
    strong = mined[
        (mined["p_hit_fdr"] < 0.05)
        & (mined["p_mean_fdr"] < 0.05)
        & (mined["hhi"] < 0.30)
        & (mined["n"] >= 15)
    ]
    edge = mined[
        ((mined["p_hit_fdr"] < 0.20) | (mined["p_mean_fdr"] < 0.20))
        & ~mined.index.isin(strong.index)
        & (mined["n"] >= 15)
    ]
    print(f"\n=== Strong candidates (FDR < 0.05 both, HHI < 0.30, n >= 15): {len(strong)} ===")
    for _, r in strong.head(10).iterrows():
        dim_values = " · ".join(
            f"{d}={r[d]}" for d in DIMENSIONS if pd.notna(r.get(d)) and r[d] != "n/a"
        )
        print(f"  [{r['n']:3d}] {dim_values}  hit={r['hit_rate']*100:.1f}% mean={r['mean_ret']*100:+.2f}%")

    print(f"\n=== Edge candidates (FDR < 0.20 either, n >= 15): {len(edge)} ===")
    for _, r in edge.head(10).iterrows():
        dim_values = " · ".join(
            f"{d}={r[d]}" for d in DIMENSIONS if pd.notna(r.get(d)) and r[d] != "n/a"
        )
        print(f"  [{r['n']:3d}] {dim_values}  hit={r['hit_rate']*100:.1f}% mean={r['mean_ret']*100:+.2f}%")

    return 0


if __name__ == "__main__":
    sys.exit(main())
