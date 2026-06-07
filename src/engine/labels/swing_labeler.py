"""Swing-label generator — ground-truth for recall analysis.

ZigZag-style pivot detection: identify alternating high/low pivots
where price reverses from the previous pivot by at least `reversal_pct`.
Adjacent confirmed pivots form a SwingLabel.

This is **ground truth for downstream recall measurement**, independent
of any engine detector. Do NOT feed engine signals into the label
algorithm — that would create circular validation.

Algorithm (single forward pass, O(n)):
  - Track current "leg" direction and the running extreme of that leg
  - Each bar may extend the leg's extreme
  - If price retraces from the leg's extreme by ≥ reversal_pct,
    confirm the extreme as a pivot, flip leg direction, start a new
    leg from that pivot
  - First pivot is identified at the first confirmed reversal

Output:
  SwingLabel(head_idx, head_price, tail_idx, tail_price, direction,
             magnitude_pct, duration_bars)
  - direction = "up" (head is low, tail is high) or "down" (head is high, tail is low)
  - magnitude_pct = |tail_price - head_price| / head_price * 100 (positive)
  - duration_bars = tail_idx - head_idx (always positive)

Reference: standard ZigZag indicator family (Achelis, TA-Lib).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

Direction = Literal["up", "down"]


@dataclass(frozen=True)
class SwingLabel:
    head_idx: int
    head_price: float
    tail_idx: int
    tail_price: float
    direction: Direction
    magnitude_pct: float       # always positive, = |tail-head|/head * 100
    duration_bars: int         # always > 0, = tail_idx - head_idx


def label_swings(
    bars: pd.DataFrame,
    *,
    reversal_pct: float = 5.0,
    min_duration_bars: int = 1,
    use_intrabar_extremes: bool = True,
) -> list[SwingLabel]:
    """Identify alternating high/low pivots and emit one SwingLabel per
    consecutive pivot pair.

    Args:
        bars: OHLC DataFrame with at minimum `high` and `low` columns
              (and `close` if `use_intrabar_extremes=False`). Index is
              positional 0..N-1 after the standard reset_index.
        reversal_pct: minimum retracement from a leg's extreme (in
              percent of that extreme) to confirm the pivot and flip
              direction. e.g. 5.0 means a 5% retracement.
        min_duration_bars: drop swings whose duration is below this
              threshold (after pivot confirmation). Default 1 keeps
              every confirmed swing.
        use_intrabar_extremes: when True, leg extremes are tracked via
              high/low (captures the full intrabar range). When False,
              only close is used (conservative, fewer pivots).

    Returns:
        List of SwingLabel ordered by head_idx ascending.
        Each label's tail_idx is the head_idx of the next label
        (consecutive pivots share endpoints).
    """
    if reversal_pct <= 0:
        raise ValueError(f"reversal_pct must be > 0 (got {reversal_pct})")
    if len(bars) < 2:
        return []

    if use_intrabar_extremes:
        if "high" not in bars.columns or "low" not in bars.columns:
            raise ValueError("bars must have 'high' and 'low' columns when use_intrabar_extremes=True")
        highs = bars["high"].to_numpy(dtype=float)
        lows = bars["low"].to_numpy(dtype=float)
    else:
        if "close" not in bars.columns:
            raise ValueError("bars must have 'close' column when use_intrabar_extremes=False")
        closes = bars["close"].to_numpy(dtype=float)
        highs = closes
        lows = closes

    # Resolve initial direction: scan forward from bar 0 until either
    # an up-reversal or down-reversal threshold is crossed. The first
    # pivot is whichever extreme is anchored at the START of the run.
    n = len(bars)
    pivots: list[tuple[int, float, str]] = []  # (idx, price, "high"|"low")

    # Initialize as undecided; track running highest-high and lowest-low
    # from the start until the first reversal confirms a direction.
    init_high_idx = 0
    init_high_val = highs[0]
    init_low_idx = 0
    init_low_val = lows[0]
    state: Literal["undecided", "up", "down"] = "undecided"
    leg_extreme_idx = 0
    leg_extreme_val = highs[0] if state == "up" else lows[0]

    for i in range(1, n):
        if np.isnan(highs[i]) or np.isnan(lows[i]):
            continue
        if state == "undecided":
            if highs[i] > init_high_val:
                init_high_val = highs[i]; init_high_idx = i
            if lows[i] < init_low_val:
                init_low_val = lows[i]; init_low_idx = i
            # Check reversal off whichever extreme came LATER (more relevant)
            # — actually, we use whichever direction crosses threshold first.
            # From running high: down-move by reversal_pct
            if init_high_val > 0 and (init_high_val - lows[i]) / init_high_val * 100 >= reversal_pct:
                # Confirm high as first pivot; new leg is down
                pivots.append((init_high_idx, init_high_val, "high"))
                state = "down"
                leg_extreme_idx = i
                leg_extreme_val = lows[i]
                continue
            # From running low: up-move by reversal_pct
            if init_low_val > 0 and (highs[i] - init_low_val) / init_low_val * 100 >= reversal_pct:
                pivots.append((init_low_idx, init_low_val, "low"))
                state = "up"
                leg_extreme_idx = i
                leg_extreme_val = highs[i]
                continue
        elif state == "up":
            if highs[i] > leg_extreme_val:
                leg_extreme_val = highs[i]
                leg_extreme_idx = i
            elif leg_extreme_val > 0 and (leg_extreme_val - lows[i]) / leg_extreme_val * 100 >= reversal_pct:
                # Confirm leg extreme as a high pivot
                pivots.append((leg_extreme_idx, leg_extreme_val, "high"))
                state = "down"
                leg_extreme_idx = i
                leg_extreme_val = lows[i]
        else:  # state == "down"
            if lows[i] < leg_extreme_val:
                leg_extreme_val = lows[i]
                leg_extreme_idx = i
            elif leg_extreme_val > 0 and (highs[i] - leg_extreme_val) / leg_extreme_val * 100 >= reversal_pct:
                pivots.append((leg_extreme_idx, leg_extreme_val, "low"))
                state = "up"
                leg_extreme_idx = i
                leg_extreme_val = highs[i]

    # Note: we do NOT append the unconfirmed last leg extreme — it may
    # still be extending. Confirmed swings only.

    # Build SwingLabels from consecutive pivot pairs
    labels: list[SwingLabel] = []
    for prev, curr in zip(pivots, pivots[1:]):
        head_idx, head_val, head_kind = prev
        tail_idx, tail_val, tail_kind = curr
        if head_kind == "low" and tail_kind == "high":
            direction: Direction = "up"
        elif head_kind == "high" and tail_kind == "low":
            direction = "down"
        else:
            # Same-kind consecutive pivots shouldn't happen with the
            # alternating algorithm above, but defend anyway
            continue
        duration = tail_idx - head_idx
        if duration < min_duration_bars:
            continue
        magnitude = abs(tail_val - head_val) / head_val * 100.0
        labels.append(SwingLabel(
            head_idx=head_idx, head_price=float(head_val),
            tail_idx=tail_idx, tail_price=float(tail_val),
            direction=direction, magnitude_pct=float(magnitude),
            duration_bars=int(duration),
        ))
    return labels


def labels_to_dataframe(labels: list[SwingLabel], bars: pd.DataFrame | None = None) -> pd.DataFrame:
    """Convenience: convert labels to DataFrame, attaching head/tail timestamps if bars provided."""
    if not labels:
        return pd.DataFrame(columns=[
            "head_idx", "head_price", "tail_idx", "tail_price",
            "direction", "magnitude_pct", "duration_bars",
        ])
    rows = [{
        "head_idx": lab.head_idx, "head_price": lab.head_price,
        "tail_idx": lab.tail_idx, "tail_price": lab.tail_price,
        "direction": lab.direction, "magnitude_pct": lab.magnitude_pct,
        "duration_bars": lab.duration_bars,
    } for lab in labels]
    df = pd.DataFrame(rows)
    if bars is not None and "timestamp" in bars.columns:
        # Use .array (not .values) to preserve tz-aware DatetimeIndex
        ts = bars["timestamp"]
        df["head_timestamp"] = ts.iloc[df["head_idx"].values].reset_index(drop=True)
        df["tail_timestamp"] = ts.iloc[df["tail_idx"].values].reset_index(drop=True)
    return df
