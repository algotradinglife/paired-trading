"""Divergence-alert chain — Xiao mechanism layer 1 + layer 3 wiring.

  divergence alert (pre-gate, both directions, classical levels only)
      × trendline break (TBreakDetector)
      → put_candidate / call_candidate ChainEvents

ALERT-ONLY: events never enter production emit lanes. Premium-space
validation happens post-migration (see
doc/design/paired_options_direction_2026-06-10.md §2.1).

Timing caveat: DivAlert.bar_idx is the divergence CANDIDATE bar
(candidate_bar_idx). Divergence detectors confirm with a lag, so a live
alert arrives later than this index. Acceptable for candidate-event lists;
the premium-space harness must re-derive live timing from raw detector
confirmation semantics before any EV claim.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from engine.divergence.detector import detect_all_divergences
from engine.divergence.tbreak_detector import TBreakSignal
from engine.features.macd import macd
from engine.features.streams import compute_feature_streams
from engine.units.snapshot import compute_unit_metadata

# Classical divergence levels only — the 6 deprecated DIF/DEA/HIST variants
# are noise for alert purposes (see score_today DIF_DETECTOR_LEVELS history).
ALERT_LEVELS: frozenset[str] = frozenset(
    {"intra_cycle", "inter_cycle", "inter_segment"})


@dataclass
class DivAlert:
    """A pre-gate divergence alert (either direction)."""
    bar_idx: int
    timestamp: pd.Timestamp
    direction: str        # "top" | "bottom"
    level: str
    subtype: str
    confidence: float


@dataclass
class ChainEvent:
    """divergence alert + trendline break paired within `lookback` bars."""
    candidate: str        # "put_candidate" | "call_candidate"
    alert: DivAlert
    tbreak: TBreakSignal
    gap_bars: int         # tbreak.bar_idx - alert.bar_idx (>= 0)


def divergence_alerts(
    bars: pd.DataFrame,
    *,
    instrument_class: str,
    level_id: str = "D",
    min_confidence: float = 0.3,
) -> list[DivAlert]:
    """Run the classical divergence detectors pre-gate, both directions."""
    macd_df = macd(bars["close"], hist_scale=1.0)
    streams = compute_feature_streams(
        bars["close"], macd_df["dif"], macd_df["dea"], macd_df["hist"])
    units = compute_unit_metadata(
        macd_df["dif"], macd_df["dea"], macd_df["hist"],
        streams["dif_proximity_zero"])
    signals = detect_all_divergences(
        units_df=units, ohlc=bars, dif=macd_df["dif"], hist=macd_df["hist"],
        level_id=level_id, instrument_class=instrument_class, gate=False)
    return [
        DivAlert(
            bar_idx=int(s.candidate_bar_idx),
            timestamp=s.timestamp,
            direction=s.direction,
            level=s.level,
            subtype=s.subtype,
            confidence=float(s.confidence),
        )
        for s in signals
        if s.level in ALERT_LEVELS and s.confidence >= min_confidence
    ]


_PAIRING: dict[str, tuple[str, str]] = {
    # tbreak.direction: (required alert direction, candidate label)
    "breakdown": ("top", "put_candidate"),
    "breakout": ("bottom", "call_candidate"),
}


def combine(
    alerts: list[DivAlert],
    tbreaks: list[TBreakSignal],
    lookback: int = 20,
) -> list[ChainEvent]:
    """Pair each tbreak with the most recent matching alert within lookback."""
    events: list[ChainEvent] = []
    for tb in tbreaks:
        want_dir, label = _PAIRING[tb.direction]
        matching = [
            a for a in alerts
            if a.direction == want_dir
            and 0 <= tb.bar_idx - a.bar_idx <= lookback
        ]
        if not matching:
            continue
        best = max(matching, key=lambda a: a.bar_idx)
        events.append(ChainEvent(
            candidate=label, alert=best, tbreak=tb,
            gap_bars=tb.bar_idx - best.bar_idx))
    return events
