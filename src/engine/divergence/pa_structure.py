"""PA (Price Action) market structure detection.

Classifies daily bars into structural phases — BULL / TR / TR_FORMING / BEAR / UNCLEAR —
using confirmed pivot highs and lows (no right-side lookahead when called in real-time).

Usage:
    det = PAStructureDetector()
    struct = det.detect(bars, up_to_idx=sig.bar_idx)
    # struct.phase, struct.tr_top, struct.tr_bot, struct.structural_stop
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


PIVOT_N    = 5    # bars each side for pivot confirmation
SEQ_WINDOW = 10   # recent mixed pivot events for phase classification
LOOKBACK   = 40   # bars to search for structural stop floor
STRUCT_BUF = 0.01 # 1% below TR floor / recent HL
TR_BOT_ZONE = 0.25  # bottom 25% of TR range counts as entry zone


@dataclass
class PAStructure:
    phase: str              # BULL | TR | TR_FORMING | BEAR | UNCLEAR
    tr_top: float | None    # ceiling of current range
    tr_bot: float | None    # floor of current range
    structural_stop: float | None  # price level for structural stop
    tr_range_pct: float | None     # range size as % of floor
    pos_in_tr: float | None        # current close position in TR (0=floor,1=ceiling)
    at_tr_bottom: bool             # close within bottom TR_BOT_ZONE of range


class PAStructureDetector:
    """Detect PA market structure at any bar index without future lookahead."""

    def __init__(
        self,
        pivot_n: int = PIVOT_N,
        seq_window: int = SEQ_WINDOW,
        lookback: int = LOOKBACK,
        struct_buf: float = STRUCT_BUF,
        tr_bot_zone: float = TR_BOT_ZONE,
    ) -> None:
        self.pivot_n    = pivot_n
        self.seq_window = seq_window
        self.lookback   = lookback
        self.struct_buf = struct_buf
        self.tr_bot_zone = tr_bot_zone

        self._cached_bars_id: int | None = None
        self._ph: list[dict] = []
        self._pl: list[dict] = []

    # ── pivot computation ─────────────────────────────────────────────────

    def _ensure_pivots(self, bars: pd.DataFrame) -> None:
        bid = id(bars)
        if bid == self._cached_bars_id:
            return
        self._ph, self._pl = self._compute_confirmed_pivots(bars)
        self._cached_bars_id = bid

    def _compute_confirmed_pivots(
        self, bars: pd.DataFrame
    ) -> tuple[list[dict], list[dict]]:
        hi  = bars["high"].values
        lo  = bars["low"].values
        n   = self.pivot_n
        ph, pl = [], []
        for i in range(n, len(bars) - n):
            if hi[i] == hi[i-n:i+n+1].max() and hi[i] > hi[i-1] and hi[i] > hi[i+1]:
                ph.append({"bar": i, "confirmed_at": i + n, "val": float(hi[i])})
            if lo[i] == lo[i-n:i+n+1].min() and lo[i] < lo[i-1] and lo[i] < lo[i+1]:
                pl.append({"bar": i, "confirmed_at": i + n, "val": float(lo[i])})
        return ph, pl

    # ── phase classification ──────────────────────────────────────────────

    @staticmethod
    def _classify_phase(avail_h: list[dict], avail_l: list[dict], window: int) -> str:
        events = [{"bar": p["bar"], "val": p["val"], "kind": "H"} for p in avail_h] + \
                 [{"bar": p["bar"], "val": p["val"], "kind": "L"} for p in avail_l]
        events.sort(key=lambda x: x["bar"])
        recent = events[-window:]
        prev_h = prev_l = None
        hh = hl = lh = ll = 0
        for e in recent:
            if e["kind"] == "H":
                if prev_h is not None:
                    if e["val"] > prev_h: hh += 1
                    else:                 lh += 1
                prev_h = e["val"]
            else:
                if prev_l is not None:
                    if e["val"] > prev_l: hl += 1
                    else:                 ll += 1
                prev_l = e["val"]
        if hh >= 2 and hl >= 2 and ll == 0 and lh <= 1:
            return "BULL"
        if lh >= 2 and ll >= 2 and hh == 0 and hl <= 1:
            return "BEAR"
        if lh >= 1 and hl >= 1 and hh == 0 and ll == 0:
            return "TR"
        if (hh >= 1 and lh >= 1) or (hl >= 1 and ll >= 1):
            return "TR_FORMING"
        return "UNCLEAR"

    # ── structural stop ───────────────────────────────────────────────────

    def _structural_stop(
        self,
        signal_bar: int,
        avail_l: list[dict],
        phase: str,
        avail_h: list[dict],
    ) -> float | None:
        if phase == "BULL":
            # Stop = most recent confirmed HL (highest of recent lows, below entry)
            hl_lows = [p for p in avail_l if signal_bar - p["bar"] <= self.lookback]
            if not hl_lows:
                hl_lows = avail_l[-3:] if len(avail_l) >= 3 else avail_l
            if not hl_lows:
                return None
            # Use the highest (most recent) low that could be an HL
            floor = max(p["val"] for p in hl_lows)
        else:
            # TR / TR_FORMING: stop below the lowest recent pivot low
            recent_l = [p for p in avail_l if signal_bar - p["bar"] <= self.lookback]
            if not recent_l:
                recent_l = avail_l[-3:] if len(avail_l) >= 3 else avail_l
            if not recent_l:
                return None
            floor = min(p["val"] for p in recent_l)
        return floor * (1 - self.struct_buf)

    # ── main API ──────────────────────────────────────────────────────────

    def detect(self, bars: pd.DataFrame, up_to_idx: int | None = None) -> PAStructure:
        """Detect PA structure at up_to_idx (defaults to last bar).

        Uses only pivots confirmed by up_to_idx (no lookahead).
        """
        if up_to_idx is None:
            up_to_idx = len(bars) - 1

        self._ensure_pivots(bars)
        avail_h = [p for p in self._ph if p["confirmed_at"] <= up_to_idx]
        avail_l = [p for p in self._pl if p["confirmed_at"] <= up_to_idx]

        if len(avail_h) < 2 or len(avail_l) < 2:
            return PAStructure(
                phase="UNCLEAR",
                tr_top=None, tr_bot=None, structural_stop=None,
                tr_range_pct=None, pos_in_tr=None, at_tr_bottom=False,
            )

        phase = self._classify_phase(avail_h, avail_l, self.seq_window)

        # TR bounds from recent pivots
        recent_h_vals = [p["val"] for p in avail_h[-8:]]
        recent_l_vals = [p["val"] for p in avail_l[-8:]]
        tr_top = max(recent_h_vals) if recent_h_vals else None
        tr_bot = min(recent_l_vals) if recent_l_vals else None

        sstop = self._structural_stop(up_to_idx, avail_l, phase, avail_h)

        cur = float(bars["close"].iloc[up_to_idx])
        if tr_top and tr_bot and tr_top > tr_bot:
            tr_range_pct = (tr_top - tr_bot) / tr_bot * 100
            pos_in_tr    = (cur - tr_bot) / (tr_top - tr_bot)
            at_tr_bot    = pos_in_tr < self.tr_bot_zone
        else:
            tr_range_pct = None
            pos_in_tr    = None
            at_tr_bot    = False

        return PAStructure(
            phase=phase,
            tr_top=tr_top,
            tr_bot=tr_bot,
            structural_stop=sstop,
            tr_range_pct=tr_range_pct,
            pos_in_tr=pos_in_tr,
            at_tr_bottom=at_tr_bot,
        )
