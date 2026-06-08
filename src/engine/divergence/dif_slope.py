"""DIF Slope Reversal (DIFSR) detector.

DEPRECATED (2026-06-08): paired-trading is moving signal generation off the
DIF-based intra_cycle_* path.  See engine.divergence.pa_* for the active
lane and doc/repro/pa_baseline_2026-06-08.md for the policy rationale.
This module is retained for historical CSV regeneration; do not extend.


Fires within a single bearish MACD cycle (DIF < 0) when the DIF's
short-term slope turns from negative to positive while price continues
to make a lower low vs the DIF-trough bar.

Complements HICD: HICD requires the histogram to recover ≥15%, which
means both DIF and DEA must have moved. DIFSR fires as soon as DIF
itself starts rising — histogram can still be deteriorating (e.g. DEA
is still falling and catching up to DIF). This can precede HICD by
1–4 bars.

Pattern:
  - DIF < 0 (current cycle is bearish)
  - Within the last LOOKBACK bars, DIF reached a trough T and the slope
    was negative at some point after T
  - Current slope (dif[i] − dif[i−SLOPE_WINDOW]) has crossed ≥ 0
  - Current bar's low is LOWER than the trough bar's low
  → Bullish divergence: DIF momentum reversing while price extends

Signal is emitted once per DIF trough (dedup by trough_abs_idx).
Subtype is always 'standard'. Confidence ∈ [0.25, 0.85] — intentionally
capped below HICD (0.90) because the signal fires with less confirmation.
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
SLOPE_WINDOW: int = 3       # bars for finite-difference slope: dif[i] - dif[i-k]
MIN_PRICE_EXT: float = 0.003  # price must be ≥ 0.3% below trough-bar low

VOLUME_LOOKBACK: int = 20


def _confidence(slope_reversal_ratio: float, price_ext: float) -> float:
    """Composite score ∈ [0.25, 0.85].

    slope_reversal_ratio: current_slope / |min_slope|
        → 0 when slope just crossed 0, 1 when slope has recovered to |min|.
    price_ext: (low_trough − low_current) / low_trough.

    Thresholds: slope recovered to 50% of |min_slope| or 3% price ext → component ≈ 1.
    """
    r = min(1.0, slope_reversal_ratio / 0.50)
    p = min(1.0, price_ext / 0.03)
    raw = 0.55 * r + 0.45 * p
    return max(0.25, min(0.85, raw))


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

def detect_dif_slope_reversal(
    ohlc: pd.DataFrame,
    dif: pd.Series,
    hist: pd.Series,
    *,
    level_id: str = "1D",
    lookback: int = LOOKBACK,
    slope_window: int = SLOPE_WINDOW,
    min_price_ext: float = MIN_PRICE_EXT,
) -> list[DivergenceSignal]:
    """Scan for DIF slope-reversal bottom signals.

    Parameters
    ----------
    ohlc : DataFrame with columns: timestamp, high, low (+ open, close, volume optional).
    dif, hist : MACD DIF and Histogram series, index-aligned with ohlc.
    level_id : timeframe label (e.g. "1D").
    lookback : bars to search backward for the DIF trough.
    slope_window : bars for finite-difference slope computation.
    min_price_ext : minimum fractional price extension below trough required.

    Returns
    -------
    list[DivergenceSignal]
    """
    ohlc = ohlc.reset_index(drop=True)
    dif = dif.reset_index(drop=True)
    hist = hist.reset_index(drop=True)

    n = len(ohlc)
    dif_arr = dif.to_numpy(dtype=float)
    low_arr = ohlc["low"].to_numpy(dtype=float)
    ts_col = ohlc["timestamp"]

    # Finite-difference slope: slope[i] = dif[i] - dif[i - slope_window]
    slope_arr = np.full(n, np.nan)
    for i in range(slope_window, n):
        if math.isfinite(dif_arr[i]) and math.isfinite(dif_arr[i - slope_window]):
            slope_arr[i] = dif_arr[i] - dif_arr[i - slope_window]

    min_lookback = max(lookback, slope_window) + 2
    signals: list[DivergenceSignal] = []
    fired_troughs: set[int] = set()

    # Pre-scan warm-up window for DIF-cycle boundary
    current_run_start: int = 0
    for j in range(min(min_lookback, n)):
        if not math.isfinite(dif_arr[j]) or dif_arr[j] >= 0:
            current_run_start = j + 1

    for i in range(min_lookback, n):
        if not math.isfinite(dif_arr[i]) or dif_arr[i] >= 0:
            current_run_start = i + 1
            continue

        # Slope must be finite and non-negative (just crossed 0 or above)
        if not math.isfinite(slope_arr[i]) or slope_arr[i] < 0:
            continue

        effective_start = max(current_run_start, i - lookback)
        if i - effective_start < slope_window + 2:
            continue

        # DIF trough: most negative DIF in window (excluding current bar)
        dif_window = dif_arr[effective_start:i]
        dif_window_clean = np.where(np.isfinite(dif_window), dif_window, 0.0)
        trough_rel = int(np.argmin(dif_window_clean))
        trough_abs = effective_start + trough_rel
        trough_dif = dif_arr[trough_abs]

        if not math.isfinite(trough_dif) or trough_dif >= 0:
            continue

        # Slope must have been negative in the window (confirms actual reversal)
        slope_window_arr = slope_arr[effective_start:i]
        if not np.any(np.where(np.isfinite(slope_window_arr), slope_window_arr, 0.0) < 0):
            continue

        min_slope_in_window = float(np.nanmin(
            np.where(np.isfinite(slope_window_arr), slope_window_arr, 0.0)
        ))
        if min_slope_in_window >= 0:
            continue  # slope never went negative in this window

        # Positive-slope component: how far above zero vs depth of the trough.
        # (total reversal ratio would always be >= 1 since slope_arr[i] >= 0,
        # saturating confidence — use positive overshoot instead)
        slope_reversal_ratio = slope_arr[i] / abs(min_slope_in_window)

        # Price: current bar must be below the trough bar's low
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
        fired_troughs.add(trough_abs)

        # Amplitude: DIF level at trough vs current (DIF is recovering in level)
        abs_trough_dif = abs(trough_dif)
        abs_current_dif = abs(dif_arr[i])
        dif_level_decay = max(0.0, (abs_trough_dif - abs_current_dif) / abs_trough_dif) if abs_trough_dif > 0 else 0.0

        conf = _confidence(slope_reversal_ratio, price_ext)

        signals.append(
            DivergenceSignal(
                level="intra_cycle_slope",
                subtype="standard",
                direction="bottom",
                level_id=level_id,
                timestamp=ts_col.iloc[i].to_pydatetime(),
                candidate_bar_idx=i,
                reference_bar_idx=trough_abs,
                container_type="dif",
                container_segment_id=-1,
                reference_id=trough_abs,
                candidate_id=i,
                price_side=PriceSide(
                    reference_value=trough_low,
                    candidate_value=current_low,
                    is_new_extreme=True,
                ),
                amplitude_side=AmplitudeSide(
                    reference_value=abs_trough_dif,
                    candidate_value=abs_current_dif,
                    decay_ratio=dif_level_decay,
                ),
                confidence=conf,
                is_continuous_gap=None,
                context_features=_context_features(ohlc, i, trough_abs),
            )
        )

    return signals
