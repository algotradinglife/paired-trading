"""Heap (量能堆) detection.

A heap is a run of consecutive same-sign Hist bars. Sub-zero gaps within a
heap (where |Hist| is briefly very small but didn't actually flip sign)
flag the heap as a "continuous gap" candidate — this is the precondition
for连续跳空 patterns later.

Reference: doc/06-vector-units.md §2

In v1 we treat any sign-zero bar as a heap boundary (strict). A future
refinement could add `max_zero_gap` tolerance per doc/06 §2.3 to merge
heaps separated only by brief mid-zero runs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Default thresholds (cf. doc/12 §4.1)
DEFAULT_NEAR_ZERO_HIST_RATIO = 0.05  # |Hist| < 5% of rolling max → "near zero bar"


def detect_heaps(
    hist: pd.Series,
    *,
    rolling_window: int = 200,
    near_zero_ratio: float = DEFAULT_NEAR_ZERO_HIST_RATIO,
) -> pd.DataFrame:
    """Vectorized per-bar heap metadata.

    A heap = a run of consecutive same-sign Hist bars. New heap when sign
    changes (or starts after a zero-sign bar). Bars where Hist == 0 exactly
    are not in any heap (heap_id = -1).

    Within each heap we track running peak |Hist| and bars-so-far counters.
    `is_continuous_gap_heap` is True for the whole heap if it contains any
    "near zero" bar (|Hist| / rolling-max-|Hist| < near_zero_ratio) at any
    point — this enables connecting "连续跳空" patterns downstream.

    Returns DataFrame indexed identically to input, with columns:
        heap_id: int                — group id; -1 if hist is exactly zero
        heap_sign: int              — +1 / -1 / 0
        heap_peak_so_far: float     — cumulative max |hist| within heap
        heap_bars_so_far: int       — 1-indexed bar count within heap
        is_continuous_gap_heap: bool — heap had a near-zero bar somewhere
    """
    if hist.empty:
        return pd.DataFrame(
            {
                "heap_id": pd.Series([], dtype=int),
                "heap_sign": pd.Series([], dtype=int),
                "heap_peak_so_far": pd.Series([], dtype=float),
                "heap_bars_so_far": pd.Series([], dtype=int),
                "is_continuous_gap_heap": pd.Series([], dtype=bool),
            }
        )

    sign = pd.Series(np.sign(hist.to_numpy()), index=hist.index).fillna(0).astype(int)

    # New heap starts whenever sign changes to a non-zero value
    sign_changed = sign != sign.shift(1).fillna(0).astype(int)
    starts_new_heap = sign_changed & (sign != 0)
    # 0-based heap IDs: cumsum gives 1 at first heap → subtract 1
    heap_id = (starts_new_heap.cumsum() - 1).astype(int)

    # Bars with sign==0 are not in any heap → mark with -1
    heap_id = heap_id.where(sign != 0, -1)

    # Within each (valid) heap, cumulative peak and bar count
    abs_hist = hist.abs()
    valid_mask = heap_id >= 0
    # When computing groupby cummax / cumsum, restrict to valid bars
    peak_so_far = (
        abs_hist.where(valid_mask, np.nan).groupby(heap_id, dropna=False).cummax()
    )
    bars_so_far = valid_mask.astype(int).groupby(heap_id, dropna=False).cumsum()

    # Mark heap-wide continuous-gap flag
    # A bar is "near zero" if |hist| / rolling_max_|hist| < threshold
    rolling_max = abs_hist.rolling(rolling_window, min_periods=1).max()
    bar_is_near_zero = (abs_hist / rolling_max.replace(0, np.nan)) < near_zero_ratio
    bar_is_near_zero = bar_is_near_zero.fillna(False) & valid_mask

    heap_has_gap = bar_is_near_zero.groupby(heap_id).transform("any")
    heap_has_gap = heap_has_gap.where(valid_mask, False).astype(bool)

    # Where not in a heap, zero out peak/bars; bars_so_far -1 means "not in heap"
    peak_so_far = peak_so_far.where(valid_mask, np.nan)
    bars_so_far = bars_so_far.where(valid_mask, 0).astype(int)

    return pd.DataFrame(
        {
            "heap_id": heap_id.astype(int),
            "heap_sign": sign.astype(int),
            "heap_peak_so_far": peak_so_far.astype(float),
            "heap_bars_so_far": bars_so_far.astype(int),
            "is_continuous_gap_heap": heap_has_gap,
        }
    )


def heap_summaries(heaps_df: pd.DataFrame, hist: pd.Series) -> pd.DataFrame:
    """Collapse per-bar heap metadata into per-heap summary rows.

    Returns one row per heap with:
        heap_id, sign, start_idx, end_idx, bars_in_heap, peak_abs_hist,
        is_continuous_gap
    """
    valid = heaps_df[heaps_df["heap_id"] >= 0].copy()
    if valid.empty:
        return pd.DataFrame(
            columns=[
                "heap_id",
                "sign",
                "start_idx",
                "end_idx",
                "bars_in_heap",
                "peak_abs_hist",
                "is_continuous_gap",
            ]
        )
    valid["bar_idx"] = valid.index

    grouped = valid.groupby("heap_id")
    summaries = pd.DataFrame(
        {
            "heap_id": grouped["heap_id"].first().astype(int),
            "sign": grouped["heap_sign"].first().astype(int),
            "start_idx": grouped["bar_idx"].first(),
            "end_idx": grouped["bar_idx"].last(),
            "bars_in_heap": grouped["heap_bars_so_far"].last().astype(int),
            "peak_abs_hist": grouped["heap_peak_so_far"].last().astype(float),
            "is_continuous_gap": grouped["is_continuous_gap_heap"].any().astype(bool),
        }
    ).reset_index(drop=True)

    return summaries
