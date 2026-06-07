"""Form detection configuration — thresholds and weights.

Defaults track doc/12-thresholds-and-params.md §3. All values are starting
points; calibration via back-test should adjust them per market/timeframe
without changing the structural code.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class HPVConfig:
    """High Position Void (高位空) configuration."""

    dif_proximity_max: float = 0.4    # DIF must be far from zero: proximity <= this
    hist_amplitude_decay_max: float = 0.4  # Hist must have decayed to <= this fraction of recent peak
    persistence_min: int = 3          # at least this many consecutive bars of decay
    weights: tuple[float, float, float, float] = (0.35, 0.35, 0.20, 0.10)


@dataclass(frozen=True)
class HiddenConfig:
    """隐形 (hidden) configuration."""

    hist_amplitude_max: float = 0.05  # |Hist| / rolling max must be < this
    persistence_min: int = 2          # bars of near-zero Hist
    price_momentum_min: float = 0.003  # |price_momentum| must exceed this
    weights: tuple[float, float, float] = (0.40, 0.30, 0.30)

    # Subtype classification thresholds (based on dif_proximity_zero)
    subtype_high_dif_proximity_max: float = 0.4    # below = "high" subtype (far from zero)
    subtype_near_zero_dif_proximity_min: float = 0.85  # above = "near_zero" subtype


@dataclass(frozen=True)
class ZeroStickConfig:
    """零轴黏合 (zero_stick) configuration."""

    dif_proximity_min: float = 0.85   # DIF must be near zero
    hist_amplitude_max: float = 0.2   # Hist relatively small
    persistence_min: int = 3
    weights: tuple[float, float, float, float] = (0.35, 0.25, 0.20, 0.20)


@dataclass(frozen=True)
class ZeroInvertedConfig:
    """零轴倒挂 (zero_inverted) configuration."""

    dif_proximity_min: float = 0.85
    persistence_min: int = 2
    weights: tuple[float, float, float] = (0.40, 0.30, 0.30)


@dataclass(frozen=True)
class NearZeroAxisConfig:
    """归零轴接近 (near_zero_axis) — dual-channel detector."""

    ema52_distance_max_pct: float = 0.02   # close within ±2% of EMA52 → channel B max
    perfect_dif_channel_min: float = 0.90   # both channels must clear these
    perfect_price_channel_min: float = 0.95


@dataclass(frozen=True)
class FormConfig:
    """Top-level container for all form-specific configs."""

    hpv: HPVConfig = field(default_factory=HPVConfig)
    hidden: HiddenConfig = field(default_factory=HiddenConfig)
    zero_stick: ZeroStickConfig = field(default_factory=ZeroStickConfig)
    zero_inverted: ZeroInvertedConfig = field(default_factory=ZeroInvertedConfig)
    near_zero: NearZeroAxisConfig = field(default_factory=NearZeroAxisConfig)


DEFAULT_FORM_CONFIG = FormConfig()
