"""Segment (线段) detection.

A segment runs from one DEA-zero-crossing to the next reverse crossing:
- "up segment"   — DEA crosses zero upward, runs while DEA > 0
- "down segment" — DEA crosses zero downward, runs while DEA < 0

In v1 we use simple sign(DEA) to partition bars. The严格穿零轴 confirmation
rules (next-bar K-line + EMA52 — see doc/07) belong to a separate layer and
will tag segments with confidence later. Here we just produce the natural
DEA-sign-based segmentation as the baseline.

Reference: doc/06-vector-units.md §4
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def detect_segments(
    dea: pd.Series,
    dif: pd.Series | None = None,
    *,
    numerical_eps: float = 1e-9,
) -> pd.DataFrame:
    """Vectorized per-bar segment metadata via DEA sign runs.

    A segment = consecutive bars where sign(DEA) is constant and non-zero.
    DEA == 0 (rare) bars are not in any segment (segment_id = -1) and break
    the run.

    Returns DataFrame indexed identically to input, with columns:
        segment_id: int                  — group id; -1 if DEA ≈ 0
        segment_direction: str           — 'up' / 'down' / 'none'
        segment_bars_so_far: int         — 1-indexed bar count within segment
        segment_peak_dif_so_far: float   — cumulative max |DIF| within segment
                                           (requires `dif` to be passed)
    """
    if dea.empty:
        return pd.DataFrame(
            {
                "segment_id": pd.Series([], dtype=int),
                "segment_direction": pd.Series([], dtype=object),
                "segment_bars_so_far": pd.Series([], dtype=int),
                "segment_peak_dif_so_far": pd.Series([], dtype=float),
            }
        )

    # Tolerance for "DEA ≈ 0" — purely numerical noise filter
    sign = np.where(
        np.abs(dea.to_numpy()) < numerical_eps,
        0,
        np.sign(dea.to_numpy()),
    ).astype(int)
    sign = pd.Series(sign, index=dea.index)

    sign_changed = sign != sign.shift(1).fillna(0).astype(int)
    starts_new = sign_changed & (sign != 0)
    # 0-based segment IDs
    segment_id = (starts_new.cumsum() - 1).astype(int)
    segment_id = segment_id.where(sign != 0, -1)

    valid_mask = segment_id >= 0
    bars_so_far = valid_mask.astype(int).groupby(segment_id, dropna=False).cumsum()
    bars_so_far = bars_so_far.where(valid_mask, 0).astype(int)

    direction = pd.Series("none", index=dea.index, dtype=object)
    direction = direction.where(sign != 1, "up")
    direction = direction.where(sign != -1, "down")

    if dif is not None:
        abs_dif = dif.abs()
        peak_dif = abs_dif.where(valid_mask, np.nan).groupby(segment_id, dropna=False).cummax()
        peak_dif = peak_dif.where(valid_mask, np.nan).astype(float)
    else:
        peak_dif = pd.Series(np.nan, index=dea.index, dtype=float)

    return pd.DataFrame(
        {
            "segment_id": segment_id.astype(int),
            "segment_direction": direction,
            "segment_bars_so_far": bars_so_far,
            "segment_peak_dif_so_far": peak_dif,
        }
    )


def segment_summaries(segments_df: pd.DataFrame) -> pd.DataFrame:
    """Collapse per-bar segment metadata into per-segment summary rows.

    Returns one row per segment with:
        segment_id, direction, start_idx, end_idx, bars_in_segment,
        peak_dif (max |DIF| within segment)
    """
    valid = segments_df[segments_df["segment_id"] >= 0].copy()
    if valid.empty:
        return pd.DataFrame(
            columns=[
                "segment_id",
                "direction",
                "start_idx",
                "end_idx",
                "bars_in_segment",
                "peak_dif",
            ]
        )
    valid["bar_idx"] = valid.index

    grouped = valid.groupby("segment_id")
    summaries = pd.DataFrame(
        {
            "segment_id": grouped["segment_id"].first().astype(int),
            "direction": grouped["segment_direction"].first(),
            "start_idx": grouped["bar_idx"].first(),
            "end_idx": grouped["bar_idx"].last(),
            "bars_in_segment": grouped["segment_bars_so_far"].last().astype(int),
            "peak_dif": grouped["segment_peak_dif_so_far"].last().astype(float),
        }
    ).reset_index(drop=True)

    return summaries
