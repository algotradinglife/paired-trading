"""Cycle (单位调整周期) detection.

A cycle runs from "DIF leaves the zero zone" to "DIF returns to the zero
zone" (confirmed for `return_confirm_bars` consecutive bars). Within a cycle
we track:

  - peak |DIF| so far
  - bar count so far
  - 1号参考点 (reference heap): the highest-peak heap within the cycle
    seen so far. Dynamically updated whenever a new heap exceeds the
    current reference's peak.

Reference: doc/06-vector-units.md §3
Reference: doc/09-divergence-detection.md §3 (reference point dynamics)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Defaults per doc/12 §4.2
DEFAULT_DEPARTURE_THRESHOLD = 0.7   # proximity must DROP BELOW this to enter a cycle
DEFAULT_RETURN_THRESHOLD = 0.9      # proximity must RISE ABOVE this for return-candidates
DEFAULT_RETURN_CONFIRM_BARS = 2     # consecutive bars above return_threshold to confirm


def detect_cycles(
    dif: pd.Series,
    dif_proximity_zero: pd.Series,
    heap_metadata: pd.DataFrame,
    *,
    departure_threshold: float = DEFAULT_DEPARTURE_THRESHOLD,
    return_threshold: float = DEFAULT_RETURN_THRESHOLD,
    return_confirm_bars: int = DEFAULT_RETURN_CONFIRM_BARS,
) -> pd.DataFrame:
    """Iterative cycle detection state machine.

    Inputs:
        dif:                  DIF series
        dif_proximity_zero:   stream 1 from feature extraction (1=at zero, 0=far)
        heap_metadata:        output of detect_heaps() — must align with dif

    Returns DataFrame indexed identically to dif, with columns:
        cycle_id: int                    — -1 if not in any cycle
        cycle_state: str                 — 'at_zero' / 'in_cycle' / 'completed'
                                           'completed' marks the last bar of the cycle
        cycle_bars_so_far: int           — 1-indexed bar count within cycle
        cycle_peak_dif_so_far: float     — cumulative max |DIF| within cycle
        cycle_reference_heap_id: int     — 1号参考点 = highest-peak heap so far in cycle
    """
    n = len(dif)
    if n == 0:
        return pd.DataFrame(
            {
                "cycle_id": pd.Series([], dtype=int),
                "cycle_state": pd.Series([], dtype=object),
                "cycle_bars_so_far": pd.Series([], dtype=int),
                "cycle_peak_dif_so_far": pd.Series([], dtype=float),
                "cycle_reference_heap_id": pd.Series([], dtype=int),
            }
        )

    proximity = dif_proximity_zero.fillna(1.0).to_numpy()  # NaN→at zero, conservative
    abs_dif = dif.abs().fillna(0.0).to_numpy()
    heap_id_arr = heap_metadata["heap_id"].to_numpy().astype(int)
    heap_peak_arr = heap_metadata["heap_peak_so_far"].fillna(0.0).to_numpy()

    cycle_ids = np.full(n, -1, dtype=int)
    cycle_states = np.full(n, "at_zero", dtype=object)
    cycle_bars = np.zeros(n, dtype=int)
    cycle_peak_dif = np.full(n, np.nan, dtype=float)
    cycle_ref_heap = np.full(n, -1, dtype=int)

    state = "at_zero"
    current_cycle_id = -1
    consecutive_returning = 0
    bars_in_cycle = 0
    peak_dif_in_cycle = 0.0
    peak_heap_val = -np.inf
    peak_heap_id = -1

    for i in range(n):
        prox = proximity[i]

        # If at_zero, check for cycle start
        if state == "at_zero":
            if prox < departure_threshold:
                # Enter new cycle
                state = "in_cycle"
                current_cycle_id += 1
                consecutive_returning = 0
                bars_in_cycle = 0
                peak_dif_in_cycle = 0.0
                peak_heap_val = -np.inf
                peak_heap_id = -1

        # If in_cycle (possibly just transitioned), update and check for end
        if state == "in_cycle":
            bars_in_cycle += 1
            peak_dif_in_cycle = max(peak_dif_in_cycle, abs_dif[i])

            # Update reference heap (1号参考点) if this bar's heap has higher peak
            if heap_id_arr[i] >= 0:
                if heap_peak_arr[i] > peak_heap_val:
                    peak_heap_val = heap_peak_arr[i]
                    peak_heap_id = heap_id_arr[i]

            # Label this bar
            cycle_ids[i] = current_cycle_id
            cycle_states[i] = "in_cycle"
            cycle_bars[i] = bars_in_cycle
            cycle_peak_dif[i] = peak_dif_in_cycle
            cycle_ref_heap[i] = peak_heap_id

            # Check return-to-zero
            if prox > return_threshold:
                consecutive_returning += 1
                if consecutive_returning >= return_confirm_bars:
                    # Confirm cycle end at this bar
                    cycle_states[i] = "completed"
                    state = "at_zero"
            else:
                consecutive_returning = 0
        # else: state stays "at_zero", labels remain defaults

    return pd.DataFrame(
        {
            "cycle_id": cycle_ids,
            "cycle_state": cycle_states,
            "cycle_bars_so_far": cycle_bars,
            "cycle_peak_dif_so_far": cycle_peak_dif,
            "cycle_reference_heap_id": cycle_ref_heap,
        },
        index=dif.index,
    )


def cycle_summaries(cycles_df: pd.DataFrame) -> pd.DataFrame:
    """Collapse per-bar cycle metadata into per-cycle summary rows.

    Returns one row per cycle with:
        cycle_id, start_idx, end_idx, bars_in_cycle, peak_dif, reference_heap_id
    """
    valid = cycles_df[cycles_df["cycle_id"] >= 0].copy()
    if valid.empty:
        return pd.DataFrame(
            columns=[
                "cycle_id",
                "start_idx",
                "end_idx",
                "bars_in_cycle",
                "peak_dif",
                "reference_heap_id",
                "is_completed",
            ]
        )
    valid["bar_idx"] = valid.index

    grouped = valid.groupby("cycle_id")
    summaries = pd.DataFrame(
        {
            "cycle_id": grouped["cycle_id"].first().astype(int),
            "start_idx": grouped["bar_idx"].first(),
            "end_idx": grouped["bar_idx"].last(),
            "bars_in_cycle": grouped["cycle_bars_so_far"].last().astype(int),
            "peak_dif": grouped["cycle_peak_dif_so_far"].last().astype(float),
            "reference_heap_id": grouped["cycle_reference_heap_id"].last().astype(int),
            "is_completed": grouped["cycle_state"].apply(lambda s: "completed" in s.values),
        }
    ).reset_index(drop=True)

    return summaries
