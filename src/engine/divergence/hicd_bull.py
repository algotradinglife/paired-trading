"""Histogram Intra-Cycle Divergence — Bullish Cycle (HICD+) detector.

DEPRECATED (2026-06-08): paired-trading is moving signal generation off the
DIF-based intra_cycle_* path.  See engine.divergence.pa_* for the active
lane and doc/repro/pa_baseline_2026-06-08.md for the policy rationale.
This module is retained for historical CSV regeneration; do not extend.


Fires within a bullish MACD cycle (DIF > 0) when the histogram (DIF − DEA gap)
has pulled back from a peak and then recovers ≥ MIN_HIST_RECOVERY of its
pullback magnitude, while price extends to a new low vs the histogram-trough bar.

Symmetrical to HICD (hicd.py) but for the DIF > 0 half of the cycle.
These are bottom signals when the histogram temporarily weakens (DIF convergence
toward DEA) but then resumes — while price has made a lower low.

Pattern:
  - DIF > 0 (bullish DIF cycle)
  - Within the last LOOKBACK bars, histogram reached a local trough T
    (histogram dropped from a positive peak, possibly even went near-zero)
  - Histogram has recovered ≥ MIN_HIST_RECOVERY of its pullback magnitude
    from T to current bar
  - Current bar's low is LOWER than the trough bar's low
  → Price/histogram divergence: histogram weakness reversing while price dips

Signal emitted once per histogram trough (dedup by trough_abs_idx).
Confidence ∈ [0.25, 0.90].
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
LOOKBACK: int = 20
MIN_HIST_RECOVERY: float = 0.15   # histogram must recover ≥ 15% of trough magnitude
MIN_PRICE_EXT: float = 0.005      # price must be ≥ 0.5% below trough-bar low
MIN_SIGNAL_GAP: int = 5

VOLUME_LOOKBACK: int = 20


def _confidence(recovery_ratio: float, price_ext: float) -> float:
    """Composite score ∈ [0.25, 0.90]."""
    r = min(1.0, recovery_ratio / 0.50)
    p = min(1.0, price_ext / 0.03)
    raw = 0.55 * r + 0.45 * p
    return max(0.25, min(0.90, raw))


def _context_features(
    ohlc: pd.DataFrame,
    candidate_idx: int,
    reference_idx: int,
) -> dict[str, float] | None:
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

    lower_wick = min(open_, close) - low
    wick_ratio = max(0.0, min(1.0, lower_wick / rng))
    feats: dict[str, float] = {
        "candidate_rejection_wick_ratio": wick_ratio,
        "invalidation_level": low,
    }

    ref_bar = ohlc.iloc[reference_idx]
    ref_low = float(ref_bar["low"])
    if ref_low > 0 and math.isfinite(ref_low):
        feats["prior_swing_distance_pct"] = (ref_low - low) / ref_low * 100.0

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

def detect_histogram_bull_divergence(
    ohlc: pd.DataFrame,
    dif: pd.Series,
    hist: pd.Series,
    *,
    level_id: str = "1D",
    lookback: int = LOOKBACK,
    min_hist_recovery: float = MIN_HIST_RECOVERY,
    min_price_ext: float = MIN_PRICE_EXT,
    min_signal_gap: int = MIN_SIGNAL_GAP,
) -> list[DivergenceSignal]:
    """Scan for histogram bullish-cycle divergence bottom signals.

    Parameters
    ----------
    ohlc : DataFrame with columns: timestamp, high, low.
    dif, hist : MACD DIF and Histogram series, index-aligned with ohlc.
    level_id : timeframe label (e.g. "1D").
    lookback : bars to search backward for the histogram trough.
    min_hist_recovery : minimum fractional recovery of trough magnitude required.
    min_price_ext : minimum fractional price extension below trough required.
    min_signal_gap : minimum bars between consecutive signals.
    """
    ohlc = ohlc.reset_index(drop=True)
    dif = dif.reset_index(drop=True)
    hist = hist.reset_index(drop=True)

    n = len(ohlc)
    dif_arr = dif.to_numpy(dtype=float)
    hist_arr = hist.to_numpy(dtype=float)
    low_arr = ohlc["low"].to_numpy(dtype=float)
    ts_col = ohlc["timestamp"]

    signals: list[DivergenceSignal] = []
    fired_troughs: set[int] = set()
    last_fire_bar: int = -min_signal_gap

    # Pre-scan warmup for DIF-cycle boundary
    current_run_start: int = 0
    for j in range(min(lookback, n)):
        if not math.isfinite(dif_arr[j]) or dif_arr[j] <= 0:
            current_run_start = j + 1

    for i in range(lookback, n):
        # Must be in a bullish DIF phase
        if not math.isfinite(dif_arr[i]) or dif_arr[i] <= 0:
            current_run_start = i + 1
            continue

        if not math.isfinite(hist_arr[i]):
            continue

        effective_start = max(current_run_start, i - lookback)
        if i - effective_start < 3:
            continue

        # Histogram pullback trough in window (most negative value in window)
        hist_window = hist_arr[effective_start:i]
        hist_clean = np.where(np.isfinite(hist_window), hist_window, np.inf)
        trough_rel = int(np.argmin(hist_clean))
        trough_abs = effective_start + trough_rel
        trough_hist = hist_arr[trough_abs]

        if not math.isfinite(trough_hist):
            continue

        # There must have been a positive histogram before the trough (confirms pullback)
        pre_trough = hist_arr[effective_start:trough_abs]
        pre_clean = np.where(np.isfinite(pre_trough), pre_trough, 0.0)
        if len(pre_clean) == 0 or not np.any(pre_clean > 0):
            continue

        peak_hist = float(np.nanmax(pre_clean))
        if peak_hist <= 0:
            continue

        # Pullback magnitude from peak to trough
        pullback = peak_hist - trough_hist
        if pullback <= 0:
            continue

        # Current histogram has recovered ≥ MIN_HIST_RECOVERY of pullback
        recovery = hist_arr[i] - trough_hist
        if recovery < min_hist_recovery * pullback:
            continue

        recovery_ratio = recovery / pullback

        # Price: current low must be below the trough bar's low
        trough_low = low_arr[trough_abs]
        current_low = low_arr[i]
        if not (math.isfinite(trough_low) and math.isfinite(current_low)):
            continue
        if current_low >= trough_low:
            continue

        price_ext = (trough_low - current_low) / trough_low
        if price_ext < min_price_ext:
            continue

        if trough_abs in fired_troughs:
            continue
        if i - last_fire_bar < min_signal_gap:
            continue
        fired_troughs.add(trough_abs)
        last_fire_bar = i

        # Amplitude: pullback-based (histogram grows during recovery in bullish phase,
        # so abs-hist decay would always be 0 — use pullback/recovery framing instead)
        recovery_capped = min(1.0, max(0.0, recovery_ratio))

        conf = _confidence(recovery_ratio, price_ext)

        signals.append(
            DivergenceSignal(
                level="intra_cycle_bull_hist",
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
                    reference_value=pullback,      # total histogram pullback magnitude
                    candidate_value=recovery,      # how much recovered at signal time
                    decay_ratio=recovery_capped,   # recovery strength [0, 1]
                ),
                confidence=conf,
                is_continuous_gap=None,
                context_features=_context_features(ohlc, i, trough_abs),
            )
        )

    return signals
