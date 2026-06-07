"""Form detection: 6 base forms from the 5 feature streams.

Reference: doc/05-form-detection.md

All forms output continuous confidences in [0, 1]. Each form is a different
weighted combination of the same 5 stream primitives + a few derived gating
conditions. The implementations follow doc/05 §2 verbatim where possible;
weights and thresholds live in `config.py` for easy retuning.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from engine.features.streams import consecutive_true_streak
from engine.forms.config import DEFAULT_FORM_CONFIG, FormConfig


def _clip01(s: pd.Series) -> pd.Series:
    """Clip a Series to the [0, 1] confidence interval."""
    return s.clip(lower=0.0, upper=1.0)


# ---------------------------------------------------------------------------
# 1. high_position
# ---------------------------------------------------------------------------

def high_position_confidence(streams: pd.DataFrame) -> pd.Series:
    """Confidence that DIF is in a "high position" (far from zero).

    Simplest form — directly the inverse of dif_proximity_zero.
    doc/05 §2.1.
    """
    return (1.0 - streams["dif_proximity_zero"]).rename("high_position").fillna(0.0)


# ---------------------------------------------------------------------------
# 2. high_position_void (HPV)
# ---------------------------------------------------------------------------

def high_position_void_confidence(
    streams: pd.DataFrame,
    *,
    config: FormConfig = DEFAULT_FORM_CONFIG,
) -> pd.Series:
    """Confidence that the bar is in High Position Void (高位空) form.

    HPV requires DIF FAR from zero as a precondition (otherwise the form
    doesn't apply — it would be 零轴黏合 / 倒挂 territory). Once that gate
    opens, the soft components combine to produce the strength of the signal:

      a) far_from_zero    = 1 - dif_proximity_zero       (how high)
      b) hist_decay       = 1 - hist_amplitude_ratio     (how decayed)
      c) same_sign        = 1 if Hist and DIF same sign  (structural req)
      d) persistence_norm = decay streak / persistence_min  (how long)

    Final: weighted sum (config.hpv.weights), gated to 0 when DIF is not in
    high position, clipped to [0, 1]. Implements doc/05 §2.2.
    """
    cfg = config.hpv
    w1, w2, w3, w4 = cfg.weights

    proximity = streams["dif_proximity_zero"].fillna(1.0)
    hist_ratio = streams["hist_amplitude_ratio"].fillna(0.0)

    # Soft components
    far_from_zero = 1.0 - proximity
    hist_decay = (1.0 - hist_ratio).clip(lower=0.0, upper=1.0)
    same_sign = (streams["hist_dif_sign_alignment"] == 1).astype(float)
    decay_streak = consecutive_true_streak(streams["hist_decaying_from_peak"])
    persistence_norm = (decay_streak / cfg.persistence_min).clip(upper=1.0)

    raw = w1 * far_from_zero + w2 * hist_decay + w3 * same_sign + w4 * persistence_norm

    # Hard form-level gate: HPV doesn't exist outside "high position" zone
    high_pos_gate = proximity <= cfg.dif_proximity_max
    gated = raw.where(high_pos_gate, 0.0)

    return _clip01(gated).rename("high_position_void")


# ---------------------------------------------------------------------------
# 3. hidden (with subtype)
# ---------------------------------------------------------------------------

def hidden_confidence(
    streams: pd.DataFrame,
    *,
    config: FormConfig = DEFAULT_FORM_CONFIG,
) -> pd.Series:
    """Confidence of `hidden` form: Hist ≈ 0 while price still moving.

    Precondition (gate): |Hist| / rolling peak < threshold. Without near-zero
    Hist, no hidden. Within the gate the score is the weighted sum of:

      a) amplitude_near_zero = 1 - hist_amplitude_ratio / threshold  (how close to 0)
      b) persistence_norm     = near-zero streak / persistence_min   (how long)
      c) momentum_magnitude   = |price_momentum| / threshold         (price moves)

    doc/05 §2.3.
    """
    cfg = config.hidden
    w1, w2, w3 = cfg.weights

    hist_ratio = streams["hist_amplitude_ratio"].fillna(0.0)

    amp_near_zero = (1.0 - hist_ratio / cfg.hist_amplitude_max).clip(lower=0.0, upper=1.0)

    near_zero_streak = consecutive_true_streak(streams["hist_near_zero"])
    persistence_norm = (near_zero_streak / cfg.persistence_min).clip(upper=1.0)

    momentum_abs = streams["price_momentum"].abs().fillna(0.0)
    momentum_magnitude = (momentum_abs / cfg.price_momentum_min).clip(upper=1.0)

    raw = w1 * amp_near_zero + w2 * persistence_norm + w3 * momentum_magnitude

    # Hard gate: no hidden if hist is not near zero
    near_zero_gate = hist_ratio < cfg.hist_amplitude_max
    gated = raw.where(near_zero_gate, 0.0)

    return _clip01(gated).rename("hidden")


def hidden_subtype(
    streams: pd.DataFrame,
    *,
    config: FormConfig = DEFAULT_FORM_CONFIG,
) -> pd.Series:
    """Classify hidden subtype per bar based on DIF position.

    Returns one of {"high", "near_zero", "none"} per bar:
      - "high"      = far from zero (proximity <= threshold)  → "必回拉零轴"
      - "near_zero" = close to zero (proximity >= threshold)  → "必穿零轴"
      - "none"      = in-between (ambiguous)
    """
    cfg = config.hidden
    proximity = streams["dif_proximity_zero"]
    subtype = pd.Series("none", index=proximity.index, dtype=object)
    subtype = subtype.where(proximity > cfg.subtype_high_dif_proximity_max, "high")
    subtype = subtype.where(
        proximity < cfg.subtype_near_zero_dif_proximity_min, "near_zero"
    )
    return subtype.rename("hidden_subtype")


# ---------------------------------------------------------------------------
# 4. zero_stick (零轴黏合)
# ---------------------------------------------------------------------------

def zero_stick_confidence(
    streams: pd.DataFrame,
    *,
    config: FormConfig = DEFAULT_FORM_CONFIG,
) -> pd.Series:
    """Confidence of `zero_stick`: DIF near zero + small Hist + same sign + persistence.

    Gate: DIF must be near zero. Otherwise this form doesn't apply.
    doc/05 §2.4.
    """
    cfg = config.zero_stick
    w1, w2, w3, w4 = cfg.weights

    proximity = streams["dif_proximity_zero"].fillna(0.0)
    hist_ratio = streams["hist_amplitude_ratio"].fillna(0.0)

    near_zero = proximity
    hist_small = (1.0 - hist_ratio / cfg.hist_amplitude_max).clip(lower=0.0, upper=1.0)
    same_sign = (streams["hist_dif_sign_alignment"] == 1).astype(float)
    near_zero_streak = consecutive_true_streak(streams["dif_near_zero"])
    persistence_norm = (near_zero_streak / cfg.persistence_min).clip(upper=1.0)

    raw = w1 * near_zero + w2 * hist_small + w3 * same_sign + w4 * persistence_norm

    gate = proximity >= cfg.dif_proximity_min
    gated = raw.where(gate, 0.0)
    return _clip01(gated).rename("zero_stick")


# ---------------------------------------------------------------------------
# 5. zero_inverted (零轴倒挂)
# ---------------------------------------------------------------------------

def zero_inverted_confidence(
    streams: pd.DataFrame,
    *,
    config: FormConfig = DEFAULT_FORM_CONFIG,
) -> pd.Series:
    """Confidence of `zero_inverted`: DIF near zero + Hist opposite-sign.

    Gates: DIF must be near zero AND Hist must be opposite-signed.
    doc/05 §2.5.
    """
    cfg = config.zero_inverted
    w1, w2, w3 = cfg.weights

    proximity = streams["dif_proximity_zero"].fillna(0.0)

    near_zero = proximity
    opposite_sign = (streams["hist_dif_sign_alignment"] == -1).astype(float)
    inverted_cond = (proximity >= cfg.dif_proximity_min) & (
        streams["hist_dif_sign_alignment"] == -1
    )
    inverted_streak = consecutive_true_streak(inverted_cond)
    persistence_norm = (inverted_streak / cfg.persistence_min).clip(upper=1.0)

    raw = w1 * near_zero + w2 * opposite_sign + w3 * persistence_norm

    gated = raw.where(inverted_cond, 0.0)
    return _clip01(gated).rename("zero_inverted")


# ---------------------------------------------------------------------------
# 6. near_zero_axis (归零轴接近) — dual-channel OR
# ---------------------------------------------------------------------------

def near_zero_axis_confidence(
    streams: pd.DataFrame,
    close: pd.Series,
    ema52: pd.Series,
    *,
    config: FormConfig = DEFAULT_FORM_CONFIG,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Compute归零轴接近 (near zero axis) signals.

    Two independent channels (doc/05 §2.6, OR relationship):
      Channel A: dif_proximity_zero (energy side)
      Channel B: 1 - |close - EMA52| / (EMA52 × tolerance%) — price side

    Returns (conf, channel_a, channel_b, perfect_flag):
      conf      = max(A, B)
      channel_a = energy side
      channel_b = price side
    "Perfect" form needs to be computed by caller: A >= 0.9 AND B >= 0.95
    """
    cfg = config.near_zero

    channel_a = streams["dif_proximity_zero"].fillna(0.0).clip(lower=0.0, upper=1.0)

    # Channel B: price closeness to EMA52
    distance_pct = (close - ema52).abs() / ema52
    channel_b = (1.0 - distance_pct / cfg.ema52_distance_max_pct).clip(lower=0.0, upper=1.0)

    conf = pd.concat([channel_a, channel_b], axis=1).max(axis=1).rename("near_zero_axis")
    return conf, channel_a.rename("near_zero_channel_a"), channel_b.rename("near_zero_channel_b")


def near_zero_perfect(
    channel_a: pd.Series,
    channel_b: pd.Series,
    *,
    config: FormConfig = DEFAULT_FORM_CONFIG,
) -> pd.Series:
    """Boolean per-bar: both归零 channels simultaneously satisfied."""
    cfg = config.near_zero
    return (
        (channel_a >= cfg.perfect_dif_channel_min)
        & (channel_b >= cfg.perfect_price_channel_min)
    ).rename("near_zero_perfect")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def compute_form_confidences(
    streams: pd.DataFrame,
    close: pd.Series,
    ema52: pd.Series,
    *,
    config: FormConfig = DEFAULT_FORM_CONFIG,
) -> pd.DataFrame:
    """Compute all 6 form confidences in one shot.

    Returns a DataFrame with columns:
        high_position             ∈ [0, 1]
        high_position_void        ∈ [0, 1]
        hidden                    ∈ [0, 1]
        hidden_subtype            {'high', 'near_zero', 'none'}
        zero_stick                ∈ [0, 1]
        zero_inverted             ∈ [0, 1]
        near_zero_axis            ∈ [0, 1]  (= max of channels A, B)
        near_zero_channel_a       ∈ [0, 1]  (energy channel)
        near_zero_channel_b       ∈ [0, 1]  (price channel)
        near_zero_perfect         bool
    """
    nz_conf, nz_a, nz_b = near_zero_axis_confidence(streams, close, ema52, config=config)
    return pd.DataFrame(
        {
            "high_position": high_position_confidence(streams),
            "high_position_void": high_position_void_confidence(streams, config=config),
            "hidden": hidden_confidence(streams, config=config),
            "hidden_subtype": hidden_subtype(streams, config=config),
            "zero_stick": zero_stick_confidence(streams, config=config),
            "zero_inverted": zero_inverted_confidence(streams, config=config),
            "near_zero_axis": nz_conf,
            "near_zero_channel_a": nz_a,
            "near_zero_channel_b": nz_b,
            "near_zero_perfect": near_zero_perfect(nz_a, nz_b, config=config),
        }
    )
