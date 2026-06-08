"""Histogram Intra-Cycle Divergence (HICD) detector.

DEPRECATED (2026-06-08): paired-trading is moving signal generation off the
DIF-based intra_cycle_* path (HICD/DIFSR/DEAD ± bull variants).  Sample-
expansion side-effects diluted the 2026-05-31 baselines (see
doc/repro/cn_b_topology_repro_2026-06-07.md).  PA detectors in
engine.divergence.pa_* are the active lane.  This module is retained for
historical CSV regeneration; do not extend.


Fires within a single bearish MACD cycle (DIF < 0) when the histogram
recovers from its local trough while price continues to make lower lows.
Unlike the standard heap-vs-heap detector, this does NOT require two
completed heaps — it fires as soon as bullish momentum divergence appears
within the cycle.

Target: the ~46% of missed swings that are 'in-cycle / bearish / down-segment'
where the heap comparator is blind because no second heap has closed.

Pattern:
  - DIF < 0 (current cycle is bearish)
  - Within the last LOOKBACK bars, histogram reached a trough T
  - Current histogram is LESS NEGATIVE than T (amplitude recovering)
  - Current bar's low is LOWER than the trough bar's low (price still declining)
  → Bullish divergence: bearish energy waning while price extends

Signal is emitted once per trough (dedup by trough_abs_idx).

Subtype is always 'standard': new price extreme (price lower) + amplitude decay
(histogram less negative). Confidence is driven by the recovery ratio and
the price extension below the trough.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from engine.divergence.signal import (
    AmplitudeSide,
    DivergenceSignal,
    PriceSide,
)

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
LOOKBACK: int = 15          # bars to look back for trough search
MIN_RECOVERY: float = 0.15  # histogram must recover ≥15% of trough depth
MIN_PRICE_EXT: float = 0.005  # price must be ≥0.5% below trough-bar low

VOLUME_LOOKBACK: int = 20


def _confidence(recovery: float, price_ext: float) -> float:
    """Composite score ∈ [0.3, 1.0].

    - recovery: (abs_trough - abs_current) / abs_trough  [0, 1]
    - price_ext: (low_trough - low_current) / low_trough  [0, …]

    Both normalised: 50% histogram recovery or 3% price extension → component ≈ 1.0.
    """
    r = min(1.0, recovery / 0.50)
    p = min(1.0, price_ext / 0.03)
    raw = 0.6 * r + 0.4 * p
    # Clamp to [0.30, 0.90] — HICD is structurally weaker than a confirmed heap.
    return max(0.30, min(0.90, raw))


def _context_features(
    ohlc: pd.DataFrame,
    candidate_idx: int,
    reference_idx: int,
) -> dict[str, float] | None:
    """Compute candle-geometry context features for the candidate bar.

    Matches the structure of _candidate_context_features() in detector.py
    (Z1–Z3 keys) so downstream consumers see a uniform dict regardless
    of which detector emitted the signal.
    """
    if "open" not in ohlc.columns or "close" not in ohlc.columns:
        return None
    bar = ohlc.iloc[candidate_idx]
    raw = (bar["high"], bar["low"], bar["open"], bar["close"])
    if any(pd.isna(v) for v in raw):
        return None

    high = float(raw[0]); low = float(raw[1])
    open_ = float(raw[2]); close = float(raw[3])
    rng = high - low
    if rng <= 0:
        return None

    # Z1: lower wick ratio (rejection of lows for a bottom)
    lower_wick = min(open_, close) - low
    wick_ratio = max(0.0, min(1.0, lower_wick / rng))

    feats: dict[str, float] = {
        "candidate_rejection_wick_ratio": wick_ratio,
        "invalidation_level": low,
    }

    # Z2b: price distance from reference (trough) to candidate bar
    ref_bar = ohlc.iloc[reference_idx]
    ref_low = float(ref_bar["low"])
    if ref_low > 0 and math.isfinite(ref_low):
        ext = (ref_low - low) / ref_low * 100.0
        feats["prior_swing_distance_pct"] = ext

    # Z3: volume ratio
    if "volume" in ohlc.columns and candidate_idx >= VOLUME_LOOKBACK:
        vol_window = ohlc["volume"].iloc[candidate_idx - VOLUME_LOOKBACK:candidate_idx]
        try:
            vol_arr = vol_window.to_numpy(dtype=float)
            cand_vol = float(ohlc["volume"].iloc[candidate_idx])
        except (TypeError, ValueError):
            vol_arr = None; cand_vol = None
        if vol_arr is not None and cand_vol is not None and not pd.isna(cand_vol):
            lb_mean = float(np.nanmean(vol_arr)) if np.any(~np.isnan(vol_arr)) else 0.0
            if lb_mean > 0:
                feats["candidate_volume_ratio"] = cand_vol / lb_mean

    return feats


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------

def detect_histogram_divergence(
    ohlc: pd.DataFrame,
    dif: pd.Series,
    hist: pd.Series,
    *,
    level_id: str = "1D",
    lookback: int = LOOKBACK,
    min_recovery: float = MIN_RECOVERY,
    min_price_ext: float = MIN_PRICE_EXT,
) -> list[DivergenceSignal]:
    """Scan `ohlc` for histogram intra-cycle divergence bottom signals.

    Parameters
    ----------
    ohlc : DataFrame with columns: timestamp, high, low (+ optionally open,
        close, volume).
    dif, hist : MACD DIF and Histogram series, index-aligned with ohlc.
    level_id : label for the timeframe (e.g. "1D").
    lookback : bars to search backward for the histogram trough.
    min_recovery : minimum fractional recovery from trough required to fire.
    min_price_ext : minimum fractional price extension below trough required.

    Returns
    -------
    list[DivergenceSignal] — one per detected trough/recovery pair.
    """
    ohlc = ohlc.reset_index(drop=True)
    dif = dif.reset_index(drop=True)
    hist = hist.reset_index(drop=True)

    dif_arr  = dif.to_numpy(dtype=float)
    hist_arr = hist.to_numpy(dtype=float)
    low_arr  = ohlc["low"].to_numpy(dtype=float)
    ts_col   = ohlc["timestamp"]

    n = len(ohlc)
    signals: list[DivergenceSignal] = []
    fired_troughs: set[int] = set()   # dedup: one signal per trough bar

    # Track the start of the current continuous DIF < 0 run so the trough
    # search never crosses into a previous cycle separated by a DIF >= 0 bar.
    # Pre-scan the warm-up window so that a cycle boundary in bars 0..lookback-1
    # is correctly reflected — without this, current_run_start would stay 0
    # even when that window contains a DIF >= 0 bar followed by DIF < 0.
    current_run_start: int = 0
    for j in range(min(lookback, n)):
        if not math.isfinite(dif_arr[j]) or dif_arr[j] >= 0:
            current_run_start = j + 1

    for i in range(lookback, n):
        # Must be in a bearish DIF phase — reset run boundary on exits
        if not math.isfinite(dif_arr[i]) or dif_arr[i] >= 0:
            current_run_start = i + 1
            continue
        # Current histogram must be negative (in a bearish heap)
        if not math.isfinite(hist_arr[i]) or hist_arr[i] >= 0:
            continue

        # Trough search is bounded by BOTH lookback AND current-run start so
        # it never spans a prior DIF cycle.  Require at least 3 bars in the
        # window (trough needs room to sit behind the current bar).
        effective_start = max(current_run_start, i - lookback)
        if i - effective_start < 3:
            continue

        # Find trough in the bounded window (excluding current bar)
        window = hist_arr[effective_start : i]
        if np.any(~np.isfinite(window)):
            window = window.copy()
            window[~np.isfinite(window)] = 0.0
        trough_rel = int(np.argmin(window))
        trough_abs = effective_start + trough_rel
        trough_hist = hist_arr[trough_abs]

        if not math.isfinite(trough_hist) or trough_hist >= 0:
            continue  # degenerate trough

        abs_trough = abs(trough_hist)
        abs_current = abs(hist_arr[i])

        # Histogram must have recovered from trough (less negative than trough)
        if abs_current >= abs_trough:
            continue  # still at or below trough — no recovery

        recovery = (abs_trough - abs_current) / abs_trough
        if recovery < min_recovery:
            continue

        # Price must be lower than at trough bar (genuine lower-low)
        trough_low = low_arr[trough_abs]
        current_low = low_arr[i]
        if not (math.isfinite(trough_low) and math.isfinite(current_low)):
            continue
        if current_low >= trough_low:
            continue

        price_ext = (trough_low - current_low) / trough_low
        if price_ext < min_price_ext:
            continue

        # Dedup: one signal per unique trough position
        if trough_abs in fired_troughs:
            continue
        fired_troughs.add(trough_abs)

        conf = _confidence(recovery, price_ext)

        signals.append(
            DivergenceSignal(
                level="intra_cycle_hist",
                subtype="standard",
                direction="bottom",
                level_id=level_id,
                timestamp=ts_col.iloc[i].to_pydatetime(),
                candidate_bar_idx=i,
                reference_bar_idx=trough_abs,
                container_type="histogram",
                container_segment_id=-1,
                reference_id=trough_abs,
                candidate_id=i,
                price_side=PriceSide(
                    reference_value=trough_low,
                    candidate_value=current_low,
                    is_new_extreme=True,
                ),
                amplitude_side=AmplitudeSide(
                    reference_value=abs_trough,
                    candidate_value=abs_current,
                    decay_ratio=recovery,
                ),
                confidence=conf,
                is_continuous_gap=None,
                context_features=_context_features(ohlc, i, trough_abs),
            )
        )

    return signals
