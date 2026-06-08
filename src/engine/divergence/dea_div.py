"""DEA Divergence (DEAD) detector.

DEPRECATED (2026-06-08): paired-trading is moving signal generation off the
DIF-based intra_cycle_* path.  See engine.divergence.pa_* for the active
lane and doc/repro/pa_baseline_2026-06-08.md for the policy rationale.
This module is retained for historical CSV regeneration; do not extend.


Fires within a single bearish MACD cycle (DIF < 0) when the DEA
(MACD signal line, slow EMA of DIF) stops declining — its slope crosses
from negative to ≥ 0 — while price continues to make a lower low vs
the DEA-trough bar.

DEA = DIF − Histogram/hist_scale, derived internally from the inputs.
Pass hist_scale matching the value used when computing the MACD histogram
(default 1.0; Aspray's original spec uses 2.0).

Relationship to other detectors:
  - DIFSR (DIF slope) fires when the fast line (DIF) first reverses.
  - DEAD fires when the slow line (DEA) reverses — typically 2–5 bars
    later, with stronger confirmation (DEA is smoother and less noisy).
  - HICD fires when the histogram (DIF − DEA gap) recovers ≥ 15% —
    this can happen BEFORE DEA reversal if DIF rises fast enough to
    widen the gap even while DEA still falls.

So the timing order is NOT strict: DIFSR → HICD → DEAD is the most
common sequence, but short-cycle regimes can invert HICD and DEAD.

Pattern:
  - DIF < 0 (bearish DIF cycle)
  - Within the last LOOKBACK bars, DEA reached a trough T
  - DEA slope (dea[i] − dea[i−SLOPE_WINDOW]) was negative at T and is
    now ≥ 0 (signal line has stopped falling)
  - Current bar's low is LOWER than the trough bar's low
  → Bullish divergence: signal-line momentum exhausted while price extends

Signal emitted once per DEA trough (dedup by trough_abs_idx).
Confidence ∈ [0.25, 0.85]; amplitude_side uses DEA slope magnitude.
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
SLOPE_WINDOW: int = 3       # bars for finite-difference slope: dea[i] - dea[i-k]
MIN_PRICE_EXT: float = 0.003  # price must be ≥ 0.3% below trough-bar low
MIN_SIGNAL_GAP: int = 5     # minimum bars between consecutive DEAD signals

VOLUME_LOOKBACK: int = 20


def _confidence(slope_reversal_ratio: float, price_ext: float) -> float:
    """Composite score ∈ [0.25, 0.85].

    slope_reversal_ratio: current_dea_slope / |min_dea_slope|
        → 0 when DEA slope just crossed 0, 1 when slope recovered to |min|.
    price_ext: (low_trough − low_current) / low_trough.

    DEA is smoother than DIF → slightly higher weight on slope component.
    Thresholds: DEA slope recovered to 50% of |min| or 3% price ext → component ≈ 1.
    """
    r = min(1.0, slope_reversal_ratio / 0.50)
    p = min(1.0, price_ext / 0.03)
    raw = 0.60 * r + 0.40 * p
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

def detect_dea_divergence(
    ohlc: pd.DataFrame,
    dif: pd.Series,
    hist: pd.Series,
    *,
    level_id: str = "1D",
    lookback: int = LOOKBACK,
    slope_window: int = SLOPE_WINDOW,
    min_price_ext: float = MIN_PRICE_EXT,
    min_signal_gap: int = MIN_SIGNAL_GAP,
    hist_scale: float = 1.0,
) -> list[DivergenceSignal]:
    """Scan for DEA signal-line divergence bottom signals.

    DEA is derived as dif − hist/hist_scale. Pass the same hist_scale used
    when computing the MACD histogram (default 1.0; Aspray's original uses 2.0).

    Parameters
    ----------
    ohlc : DataFrame with columns: timestamp, high, low.
    dif, hist : MACD DIF and Histogram series, index-aligned with ohlc.
    level_id : timeframe label (e.g. "1D").
    lookback : bars to search backward for the DEA trough.
    slope_window : bars for finite-difference slope computation.
    min_price_ext : minimum fractional price extension below trough required.
    hist_scale : histogram scaling factor used when hist was computed
        (hist = hist_scale * (dif − dea), so dea = dif − hist/hist_scale).

    Returns
    -------
    list[DivergenceSignal]
    """
    ohlc = ohlc.reset_index(drop=True)
    dif = dif.reset_index(drop=True)
    hist = hist.reset_index(drop=True)

    n = len(ohlc)
    dif_arr = dif.to_numpy(dtype=float)
    hist_arr = hist.to_numpy(dtype=float)
    # DEA = DIF − Histogram / hist_scale
    dea_arr = np.where(
        np.isfinite(dif_arr) & np.isfinite(hist_arr),
        dif_arr - hist_arr / hist_scale,
        np.nan,
    )
    low_arr = ohlc["low"].to_numpy(dtype=float)
    ts_col = ohlc["timestamp"]

    # Finite-difference DEA slope
    dea_slope_arr = np.full(n, np.nan)
    for i in range(slope_window, n):
        if math.isfinite(dea_arr[i]) and math.isfinite(dea_arr[i - slope_window]):
            dea_slope_arr[i] = dea_arr[i] - dea_arr[i - slope_window]

    min_lookback = max(lookback, slope_window) + 2
    signals: list[DivergenceSignal] = []
    fired_troughs: set[int] = set()
    last_fire_bar: int = -min_signal_gap  # tracks cooldown

    # Pre-scan warm-up window for DIF-cycle boundary
    current_run_start: int = 0
    for j in range(min(min_lookback, n)):
        if not math.isfinite(dif_arr[j]) or dif_arr[j] >= 0:
            current_run_start = j + 1

    for i in range(min_lookback, n):
        # Must be in a bearish DIF phase
        if not math.isfinite(dif_arr[i]) or dif_arr[i] >= 0:
            current_run_start = i + 1
            continue

        # DEA slope must be finite and non-negative (just stopped declining)
        if not math.isfinite(dea_slope_arr[i]) or dea_slope_arr[i] < 0:
            continue

        effective_start = max(current_run_start, i - lookback)
        if i - effective_start < slope_window + 2:
            continue

        # DEA trough: most negative DEA in window (excluding current bar)
        dea_window = dea_arr[effective_start:i]
        dea_window_clean = np.where(np.isfinite(dea_window), dea_window, 0.0)
        trough_rel = int(np.argmin(dea_window_clean))
        trough_abs = effective_start + trough_rel
        trough_dea = dea_arr[trough_abs]

        if not math.isfinite(trough_dea) or trough_dea >= 0:
            continue

        # DEA slope must have been negative in window (confirms actual reversal)
        dea_slope_window = dea_slope_arr[effective_start:i]
        dea_slope_clean = np.where(np.isfinite(dea_slope_window), dea_slope_window, 0.0)
        if not np.any(dea_slope_clean < 0):
            continue

        min_dea_slope = float(np.nanmin(dea_slope_clean))
        if min_dea_slope >= 0:
            continue

        # Positive-slope component: how far above zero vs depth of the trough.
        # (total reversal ratio would always be >= 1 since dea_slope_arr[i] >= 0,
        # saturating confidence — use positive overshoot instead)
        slope_reversal_ratio = dea_slope_arr[i] / abs(min_dea_slope)

        # Price: current low must be below DEA-trough bar's low
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

        # Amplitude: DEA slope magnitude (most negative → near zero)
        abs_min_dea_slope = abs(min_dea_slope)
        abs_current_dea_slope = abs(dea_slope_arr[i])
        slope_decay = max(0.0, (abs_min_dea_slope - abs_current_dea_slope) / abs_min_dea_slope)

        conf = _confidence(slope_reversal_ratio, price_ext)

        signals.append(
            DivergenceSignal(
                level="intra_cycle_dea",
                subtype="standard",
                direction="bottom",
                level_id=level_id,
                timestamp=ts_col.iloc[i].to_pydatetime(),
                candidate_bar_idx=i,
                reference_bar_idx=trough_abs,
                container_type="dea",
                container_segment_id=-1,
                reference_id=trough_abs,
                candidate_id=i,
                price_side=PriceSide(
                    reference_value=trough_low,
                    candidate_value=current_low,
                    is_new_extreme=True,
                ),
                amplitude_side=AmplitudeSide(
                    reference_value=abs_min_dea_slope,
                    candidate_value=abs_current_dea_slope,
                    decay_ratio=slope_decay,
                ),
                confidence=conf,
                is_continuous_gap=None,
                context_features=_context_features(ohlc, i, trough_abs),
            )
        )

    return signals
