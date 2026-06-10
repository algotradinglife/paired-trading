# Phase A — Trendline-Break + Divergence Alert Chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Xiao right-side confirmation chain — MACD divergence alert → trendline break → put/call candidate events — as alert-only machinery (policy_weight=0, no production lanes, no EV claims).

**Architecture:** Pure geometry layer (`engine/features/trendline.py`) → detector following bpull/vflush conventions (`engine/divergence/tbreak_detector.py`) → chain combiner using pre-gate divergences (`engine/divergence/alert_chain.py`) → full-pool scan script (`scripts/scan_tbreak_chain.py`). All causal (pivot `confirmed_at = idx + n`).

**Tech Stack:** Python 3.12, pandas/numpy, pytest, uv. VCS is **jj** (never git write commands). Run tests from `src/`: `cd /Users/huhan/code/trading/paired-trading/src && uv run pytest ...`

**Spec:** `docs/superpowers/specs/2026-06-10-phase-a-tbreak-chain-design.md`

**Conventions verified against:**
- bars = `pd.DataFrame` with tz-aware UTC `timestamp`, `open/high/low/close` (`bar_loader.load_bars_quant_or_json(sym, suffix, bars_dir)`)
- detector pattern = `bpull_detector.py` (dataclass signal, `scan(bars, h_bars=None)`, static `policy_weight`)
- divergence pipeline call = `score_today.py:867-873`
- `DivergenceSignal` fields used: `candidate_bar_idx`, `timestamp`, `direction`, `level`, `subtype`, `confidence`
- POOLS / POOL_INSTRUMENT_CLASS = `score_today.py:96-117`

---

### Task 1: Trendline geometry (`engine/features/trendline.py`)

**Files:**
- Create: `src/engine/features/trendline.py`
- Test: `src/tests/test_trendline.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for engine/features/trendline.py — pivot-pair trendline geometry."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.features.trendline import Trendline, fit_trendline


def make_bars(rows: list[tuple[float, float, float]]) -> pd.DataFrame:
    """rows = (high, low, close). Timestamps daily UTC from 2024-01-01."""
    ts = pd.date_range("2024-01-01", periods=len(rows), freq="D", tz="UTC")
    return pd.DataFrame({
        "timestamp": ts,
        "open":  [c for _, _, c in rows],
        "high":  [h for h, _, _ in rows],
        "low":   [l for _, l, _ in rows],
        "close": [c for _, _, c in rows],
    })


# Rising support fixture, pivot_n=2.
# Pivot lows: idx2 (low=8.0, confirmed at 4), idx7 (low=9.5, confirmed at 9).
# Support line: (2, 8.0) -> (7, 9.5), slope=0.3/bar.
UPTREND_ROWS = [
    # (high,  low,  close)
    (11.0, 10.0, 10.5),   # 0
    (10.5,  9.0,  9.5),   # 1
    ( 9.5,  8.0,  9.0),   # 2  pivot low (8.0)
    (10.5,  9.0, 10.0),   # 3
    (11.5, 10.0, 11.0),   # 4
    (12.0, 11.0, 11.5),   # 5
    (11.5, 10.0, 11.0),   # 6
    (10.8,  9.5, 10.2),   # 7  pivot low (9.5)
    (11.5, 10.5, 11.0),   # 8
    (12.5, 11.5, 12.0),   # 9  pivot idx7 confirmed here
    (13.0, 12.0, 12.5),   # 10
    (13.0, 12.0, 12.2),   # 11
    (12.5, 11.8, 12.0),   # 12  line value = 8 + 0.3*10 = 11.0; close 12.0 above
]


def test_value_at_interpolates_and_extrapolates():
    tl = Trendline(kind="support", idx1=2, price1=8.0, idx2=7, price2=9.5)
    assert tl.slope == pytest.approx(0.3)
    assert tl.value_at(7) == pytest.approx(9.5)
    assert tl.value_at(12) == pytest.approx(11.0)


def test_fit_support_line_on_rising_lows():
    bars = make_bars(UPTREND_ROWS)
    tl = fit_trendline(bars, up_to_idx=12, kind="support", pivot_n=2)
    assert tl is not None
    assert (tl.idx1, tl.price1) == (2, 8.0)
    assert (tl.idx2, tl.price2) == (7, 9.5)


def test_fit_requires_confirmed_pivots():
    bars = make_bars(UPTREND_ROWS)
    # At up_to_idx=8 the idx7 pivot is NOT yet confirmed (needs idx 9).
    tl = fit_trendline(bars, up_to_idx=8, kind="support", pivot_n=2)
    assert tl is None or tl.idx2 != 7


def test_fit_returns_none_when_lows_not_rising():
    rows = [(r[0], r[1], r[2]) for r in UPTREND_ROWS]
    # Make second pivot LOWER than first (9.5 -> 7.0): not a rising support.
    rows[7] = (10.8, 7.0, 10.2)
    bars = make_bars(rows)
    tl = fit_trendline(bars, up_to_idx=12, kind="support", pivot_n=2)
    assert tl is None


def test_fit_resistance_line_on_falling_highs():
    # Mirror image: falling pivot highs at idx2 (12.0) and idx7 (10.5).
    rows = [
        ( 9.0,  8.0,  8.5),   # 0
        (10.5,  9.5, 10.0),   # 1
        (12.0, 10.5, 11.0),   # 2  pivot high (12.0)
        (10.5,  9.0,  9.5),   # 3
        ( 9.5,  8.0,  8.5),   # 4
        ( 9.0,  7.5,  8.0),   # 5
        ( 9.5,  8.0,  9.0),   # 6
        (10.5,  9.0,  9.8),   # 7  pivot high (10.5)
        ( 9.5,  8.0,  8.5),   # 8
        ( 8.5,  7.0,  7.5),   # 9
        ( 8.0,  6.5,  7.0),   # 10
    ]
    bars = make_bars(rows)
    tl = fit_trendline(bars, up_to_idx=10, kind="resistance", pivot_n=2)
    assert tl is not None
    assert (tl.idx1, tl.price1) == (2, 12.0)
    assert (tl.idx2, tl.price2) == (7, 10.5)
    assert tl.slope == pytest.approx(-0.3)


def test_causality_prefix_invariance():
    """Fitting at up_to_idx=k must not change when future bars are appended."""
    bars = make_bars(UPTREND_ROWS)
    full = fit_trendline(bars, up_to_idx=10, kind="support", pivot_n=2)
    prefix = fit_trendline(bars.iloc[:11].reset_index(drop=True), up_to_idx=10,
                           kind="support", pivot_n=2)
    assert (full is None) == (prefix is None)
    if full is not None:
        assert (full.idx1, full.price1, full.idx2, full.price2) == \
               (prefix.idx1, prefix.price1, prefix.idx2, prefix.price2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/huhan/code/trading/paired-trading/src && uv run pytest tests/test_trendline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.features.trendline'`

- [ ] **Step 3: Implement `src/engine/features/trendline.py`**

```python
"""Pivot-pair trendlines — Xiao right-side confirmation geometry.

A trendline connects the two most recent CONFIRMED fractal pivots of the
same kind:
  support    = two rising swing lows  (older lower, newer higher)
  resistance = two falling swing highs (older higher, newer lower)

Causal: a pivot at index p with half-width n is confirmed at p + n; only
pivots with p + n <= up_to_idx are used. Spec:
docs/superpowers/specs/2026-06-10-phase-a-tbreak-chain-design.md
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Trendline:
    """Line through two anchor pivots, extrapolated forward."""
    kind: str          # "support" | "resistance"
    idx1: int          # older anchor bar index
    price1: float
    idx2: int          # newer anchor bar index
    price2: float

    @property
    def slope(self) -> float:
        return (self.price2 - self.price1) / (self.idx2 - self.idx1)

    def value_at(self, idx: int) -> float:
        return self.price1 + self.slope * (idx - self.idx1)


def _confirmed_pivots(
    values: np.ndarray, n: int, up_to_idx: int, find_high: bool,
) -> list[int]:
    """Fractal pivots confirmed by up_to_idx (pivot p needs p+n <= up_to_idx).

    Pivot rule mirrors swing_context.detect_swing_points: strictly greater
    (resp. smaller) than the n bars on each side.
    """
    out: list[int] = []
    last = min(up_to_idx - n, len(values) - 1 - n)
    for i in range(n, last + 1):
        v = values[i]
        left = values[i - n:i]
        right = values[i + 1:i + n + 1]
        if find_high:
            if np.all(v > left) and np.all(v > right):
                out.append(i)
        else:
            if np.all(v < left) and np.all(v < right):
                out.append(i)
    return out


def fit_trendline(
    bars: pd.DataFrame,
    up_to_idx: int,
    kind: str,
    pivot_n: int = 5,
) -> Trendline | None:
    """Fit the most recent valid 2-pivot trendline as of bar up_to_idx.

    support:    most recent pivot-low pair (older_low < newer_low)
    resistance: most recent pivot-high pair (older_high > newer_high)
    Returns None when no such pair exists among confirmed pivots.
    """
    if kind not in ("support", "resistance"):
        raise ValueError(f"unknown trendline kind: {kind!r}")

    find_high = kind == "resistance"
    col = "high" if find_high else "low"
    values = bars[col].values.astype(float)
    pivots = _confirmed_pivots(values, pivot_n, up_to_idx, find_high)
    if len(pivots) < 2:
        return None

    # Scan pairs from the most recent backwards: (p1 older, p2 newer).
    for j in range(len(pivots) - 1, 0, -1):
        p2 = pivots[j]
        for i in range(j - 1, -1, -1):
            p1 = pivots[i]
            rising = values[p2] > values[p1]
            if (kind == "support" and rising) or (kind == "resistance" and not rising):
                return Trendline(
                    kind=kind,
                    idx1=p1, price1=float(values[p1]),
                    idx2=p2, price2=float(values[p2]),
                )
        # Newest pivot has no valid partner — older pairs would be stale lines;
        # fall through and try the previous pivot as p2.
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/huhan/code/trading/paired-trading/src && uv run pytest tests/test_trendline.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/huhan/code/trading/paired-trading
jj describe -m "feat(trendline): pivot-pair trendline geometry (Phase A tbreak chain)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" && jj new
```

---

### Task 2: TBreakDetector (`engine/divergence/tbreak_detector.py`)

**Files:**
- Create: `src/engine/divergence/tbreak_detector.py`
- Test: `src/tests/test_tbreak_detector.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for TBreakDetector — trendline-break alert detector."""
from __future__ import annotations

import pandas as pd
import pytest

from engine.divergence.tbreak_detector import TBreakDetector, TBreakSignal
from tests.test_trendline import make_bars, UPTREND_ROWS


def breakdown_rows() -> list[tuple[float, float, float]]:
    """UPTREND_ROWS + a clean close below the support line at idx 13.

    Line (2,8.0)->(7,9.5) has value 8 + 0.3*11 = 11.3 at idx 13.
    Close 9.0 is far below value - buffer for any sane ATR buffer.
    """
    return UPTREND_ROWS + [(11.0, 8.8, 9.0)]   # idx 13


def test_emits_breakdown_below_support():
    det = TBreakDetector(pivot_n=2, buffer_atr=0.1, confirm_bars=1, min_gap=5)
    sigs = det.scan(make_bars(breakdown_rows()))
    breakdowns = [s for s in sigs if s.direction == "breakdown"]
    assert len(breakdowns) == 1
    assert breakdowns[0].bar_idx == 13
    f = breakdowns[0].features
    assert f["kind"] == "support"
    assert f["anchor_idx1"] == 2 and f["anchor_idx2"] == 7
    assert f["line_value"] == pytest.approx(11.3)


def test_no_signal_when_close_stays_above_line():
    det = TBreakDetector(pivot_n=2, buffer_atr=0.1, confirm_bars=1, min_gap=5)
    sigs = det.scan(make_bars(UPTREND_ROWS))
    assert [s for s in sigs if s.direction == "breakdown"] == []


def test_buffer_blocks_marginal_break():
    """A close a hair below the line must NOT fire (within ATR buffer)."""
    rows = UPTREND_ROWS + [(12.0, 11.0, 11.25)]  # idx13, line=11.3, gap=0.05
    det = TBreakDetector(pivot_n=2, buffer_atr=10.0,  # huge buffer
                         confirm_bars=1, min_gap=5)
    sigs = det.scan(make_bars(rows))
    assert [s for s in sigs if s.direction == "breakdown"] == []


def test_same_line_fires_once():
    """Bars keep closing below the same line — only one signal per anchor pair."""
    rows = breakdown_rows() + [(10.0, 8.5, 8.8), (9.5, 8.0, 8.5)]  # idx 14, 15
    det = TBreakDetector(pivot_n=2, buffer_atr=0.1, confirm_bars=1, min_gap=1)
    sigs = det.scan(make_bars(rows))
    assert len([s for s in sigs if s.direction == "breakdown"]) == 1


def test_confirm_bars_2_cancels_on_reclaim():
    """confirm_bars=2: candidate at idx13, reclaim above line at idx14 -> no signal."""
    rows = breakdown_rows() + [(13.0, 11.5, 12.5)]  # idx14 closes back above
    det = TBreakDetector(pivot_n=2, buffer_atr=0.1, confirm_bars=2, min_gap=5)
    sigs = det.scan(make_bars(rows))
    assert [s for s in sigs if s.direction == "breakdown"] == []


def test_confirm_bars_2_fires_on_followthrough():
    rows = breakdown_rows() + [(9.5, 8.2, 8.6)]  # idx14 stays below
    det = TBreakDetector(pivot_n=2, buffer_atr=0.1, confirm_bars=2, min_gap=5)
    sigs = det.scan(make_bars(rows))
    breakdowns = [s for s in sigs if s.direction == "breakdown"]
    assert len(breakdowns) == 1
    assert breakdowns[0].bar_idx == 14


def test_causality_prefix_invariance():
    rows = breakdown_rows() + [(10.0, 8.5, 8.8), (9.5, 8.0, 8.5)]
    det = TBreakDetector(pivot_n=2, buffer_atr=0.1, confirm_bars=1, min_gap=5)
    full = det.scan(make_bars(rows))
    prefix = det.scan(make_bars(rows[:14]))
    full_upto = [(s.bar_idx, s.direction) for s in full if s.bar_idx <= 13]
    pref = [(s.bar_idx, s.direction) for s in prefix]
    assert full_upto == pref


def test_policy_weight_always_zero():
    det = TBreakDetector(pivot_n=2)
    sigs = det.scan(make_bars(breakdown_rows()))
    assert sigs and TBreakDetector.policy_weight(sigs[0], "cn_futures", "kq_m_shfe_rb") == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/huhan/code/trading/paired-trading/src && uv run pytest tests/test_tbreak_detector.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.divergence.tbreak_detector'`

- [ ] **Step 3: Implement `src/engine/divergence/tbreak_detector.py`**

```python
"""TBreak — trendline-break detector (Xiao right-side confirmation).

ALERT-ONLY: policy_weight is hard 0.0. This detector never enters the
production emit lanes / R-space scoring. Its events feed the
divergence-alert chain (engine/divergence/alert_chain.py) whose output is
validated post-migration in option-premium space.

Pattern:
  breakdown — close < rising-support-line value − buffer  (put-candidate leg)
  breakout  — close > falling-resistance-line value + buffer (call-candidate leg)
  buffer = buffer_atr × ATR(atr_period), guards against hairline fake breaks.
  confirm_bars=2 requires the next close to hold beyond the line (reclaim
  cancels). Each anchor pair fires at most once; min_gap spaces same-direction
  signals.

Spec: docs/superpowers/specs/2026-06-10-phase-a-tbreak-chain-design.md
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from engine.features.trendline import Trendline, fit_trendline


@dataclass
class TBreakSignal:
    """A trendline-break event.

    direction: "breakdown" (support broken) | "breakout" (resistance broken)
    features:  kind, anchor_idx1/2, anchor_price1/2, slope, line_value,
               buffer_abs, atr, close, touches
    """
    bar_idx: int
    timestamp: pd.Timestamp
    direction: str
    features: dict[str, object] = field(default_factory=dict)


def _compute_atr(bars: pd.DataFrame, period: int) -> pd.Series:
    hi, lo, pc = bars["high"], bars["low"], bars["close"].shift(1)
    tr = pd.concat([(hi - lo), (hi - pc).abs(), (lo - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


class TBreakDetector:
    """Trendline-break detector on pivot-pair lines. Alert-only.

    Args:
        pivot_n:      fractal half-width for pivot confirmation (default 5)
        buffer_atr:   break must clear line by buffer_atr × ATR (default 0.1)
        confirm_bars: 1 = close beyond line fires; 2 = next close must hold
        min_gap:      minimum bars between same-direction signals
        atr_period:   ATR period for the buffer (default 14)
    """

    def __init__(
        self,
        pivot_n: int = 5,
        buffer_atr: float = 0.1,
        confirm_bars: int = 1,
        min_gap: int = 10,
        atr_period: int = 14,
    ) -> None:
        if confirm_bars not in (1, 2):
            raise ValueError("confirm_bars must be 1 or 2")
        self.pivot_n = pivot_n
        self.buffer_atr = buffer_atr
        self.confirm_bars = confirm_bars
        self.min_gap = min_gap
        self.atr_period = atr_period

    def scan(
        self,
        bars: pd.DataFrame,
        h_bars: pd.DataFrame | None = None,  # unused; detector-API symmetry
    ) -> list[TBreakSignal]:
        closes = bars["close"].values.astype(float)
        atr = _compute_atr(bars, self.atr_period).values
        ts = bars["timestamp"]
        n = len(bars)

        signals: list[TBreakSignal] = []
        fired: set[tuple[str, int, int]] = set()   # (kind, idx1, idx2)
        last_fire: dict[str, int] = {}             # direction -> bar_idx
        # pending[direction] = (line, candidate_idx) awaiting follow-through
        pending: dict[str, tuple[Trendline, int]] = {}

        specs = (
            ("support", "breakdown", -1.0),
            ("resistance", "breakout", +1.0),
        )

        for i in range(2 * self.pivot_n + 1, n):
            for kind, direction, sgn in specs:
                # --- resolve pending confirm_bars=2 candidates first
                if direction in pending:
                    line, cand = pending.pop(direction)
                    beyond = sgn * (closes[i] - line.value_at(i)) > 0.0
                    if beyond:
                        signals.append(self._make_signal(
                            line, i, ts.iloc[i], direction, closes[i], atr[i], bars))
                        fired.add((line.kind, line.idx1, line.idx2))
                        last_fire[direction] = i
                    continue  # reclaim -> candidate cancelled, nothing fires

                line = fit_trendline(bars, up_to_idx=i, kind=kind, pivot_n=self.pivot_n)
                if line is None or (line.kind, line.idx1, line.idx2) in fired:
                    continue
                if direction in last_fire and i - last_fire[direction] < self.min_gap:
                    continue
                buffer_abs = self.buffer_atr * float(atr[i])
                crossed = sgn * (closes[i] - line.value_at(i)) > buffer_abs
                if not crossed:
                    continue
                if self.confirm_bars == 2:
                    pending[direction] = (line, i)
                else:
                    signals.append(self._make_signal(
                        line, i, ts.iloc[i], direction, closes[i], atr[i], bars))
                    fired.add((line.kind, line.idx1, line.idx2))
                    last_fire[direction] = i

        return signals

    def _make_signal(
        self, line: Trendline, i: int, timestamp: pd.Timestamp,
        direction: str, close: float, atr_i: float, bars: pd.DataFrame,
    ) -> TBreakSignal:
        touch_col = "low" if line.kind == "support" else "high"
        vals = bars[touch_col].values.astype(float)
        tol = self.buffer_atr * atr_i
        touches = sum(
            1 for j in range(line.idx2 + 1, i)
            if abs(vals[j] - line.value_at(j)) <= tol
        )
        return TBreakSignal(
            bar_idx=i,
            timestamp=timestamp,
            direction=direction,
            features={
                "kind": line.kind,
                "anchor_idx1": line.idx1, "anchor_price1": line.price1,
                "anchor_idx2": line.idx2, "anchor_price2": line.price2,
                "slope": line.slope,
                "line_value": line.value_at(i),
                "buffer_abs": self.buffer_atr * atr_i,
                "atr": float(atr_i),
                "close": float(close),
                "touches": touches,
            },
        )

    @staticmethod
    def policy_weight(sig: TBreakSignal, instrument_class: str, symbol: str) -> float:
        """Alert-only detector: never weighted into production scoring."""
        return 0.0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/huhan/code/trading/paired-trading/src && uv run pytest tests/test_tbreak_detector.py tests/test_trendline.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
cd /Users/huhan/code/trading/paired-trading
jj describe -m "feat(tbreak): trendline-break alert detector, policy_weight=0

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" && jj new
```

---

### Task 3: Pre-gate divergence access (`detector.py` gate param)

**Files:**
- Modify: `src/engine/divergence/detector.py:450-493` (`detect_all_divergences`)
- Test: `src/tests/test_alert_chain.py` (first test only; file grows in Task 4)

- [ ] **Step 1: Write the failing test**

Create `src/tests/test_alert_chain.py`:

```python
"""Tests for the divergence-alert chain (pre-gate alerts + tbreak combine)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.divergence.detector import detect_all_divergences
from engine.features.macd import macd
from engine.features.streams import compute_feature_streams
from engine.units.snapshot import compute_unit_metadata


def random_walk_bars(n: int = 400, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100.0 + np.cumsum(rng.normal(0, 1.0, n))
    high = close + rng.uniform(0.2, 1.5, n)
    low = close - rng.uniform(0.2, 1.5, n)
    ts = pd.date_range("2022-01-03", periods=n, freq="D", tz="UTC")
    return pd.DataFrame({"timestamp": ts, "open": close, "high": high,
                         "low": low, "close": close})


def _divergence_signals(bars: pd.DataFrame, gate: bool):
    macd_df = macd(bars["close"], hist_scale=1.0)
    streams = compute_feature_streams(
        bars["close"], macd_df["dif"], macd_df["dea"], macd_df["hist"])
    units = compute_unit_metadata(
        macd_df["dif"], macd_df["dea"], macd_df["hist"],
        streams["dif_proximity_zero"])
    return detect_all_divergences(
        units_df=units, ohlc=bars, dif=macd_df["dif"], hist=macd_df["hist"],
        level_id="D", instrument_class="us_equity", gate=gate)


def test_gate_false_is_superset_of_gate_true():
    bars = random_walk_bars()
    gated = _divergence_signals(bars, gate=True)
    raw = _divergence_signals(bars, gate=False)
    assert len(raw) >= len(gated)
    # us_equity gate drops/de-weights tops; raw must keep at least as many tops
    raw_tops = [s for s in raw if s.direction == "top"]
    gated_tops = [s for s in gated if s.direction == "top"]
    assert len(raw_tops) >= len(gated_tops)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/huhan/code/trading/paired-trading/src && uv run pytest tests/test_alert_chain.py -v`
Expected: FAIL — `TypeError: detect_all_divergences() got an unexpected keyword argument 'gate'`

- [ ] **Step 3: Add the `gate` parameter**

In `src/engine/divergence/detector.py`, change the signature (line ~450):

```python
def detect_all_divergences(
    units_df: pd.DataFrame,
    ohlc: pd.DataFrame,
    dif: pd.Series,
    hist: pd.Series,
    *,
    level_id: str = "1D",
    instrument_class: str = "us_equity",
    gate: bool = True,
) -> list[DivergenceSignal]:
```

and the gate call (line ~491):

```python
    if gate:
        signals = gate_signals(signals, instrument_class=instrument_class)
```

Append to the docstring:

```
    `gate=False` returns the raw pre-direction-gate signals — used by the
    alert layer (engine/divergence/alert_chain.py), which needs top signals
    at raw confidence. Production callers keep the default gate=True.
```

- [ ] **Step 4: Run tests — new test passes, no regression**

Run: `cd /Users/huhan/code/trading/paired-trading/src && uv run pytest tests/test_alert_chain.py tests/test_divergence.py -v`
Expected: all passed (gate default unchanged ⇒ zero behavior change for existing callers)

- [ ] **Step 5: Commit**

```bash
cd /Users/huhan/code/trading/paired-trading
jj describe -m "feat(divergence): gate=False param for pre-gate alert access

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" && jj new
```

---

### Task 4: Alert chain (`engine/divergence/alert_chain.py`)

**Files:**
- Create: `src/engine/divergence/alert_chain.py`
- Modify: `src/tests/test_alert_chain.py` (append tests)

- [ ] **Step 1: Append the failing tests to `src/tests/test_alert_chain.py`**

```python
from engine.divergence.alert_chain import (
    ChainEvent, DivAlert, combine, divergence_alerts,
)
from engine.divergence.tbreak_detector import TBreakSignal


def _alert(bar_idx: int, direction: str) -> DivAlert:
    return DivAlert(bar_idx=bar_idx,
                    timestamp=pd.Timestamp("2024-01-01", tz="UTC"),
                    direction=direction, level="intra_cycle",
                    subtype="standard", confidence=0.6)


def _tbreak(bar_idx: int, direction: str) -> TBreakSignal:
    return TBreakSignal(bar_idx=bar_idx,
                        timestamp=pd.Timestamp("2024-02-01", tz="UTC"),
                        direction=direction, features={})


def test_combine_top_plus_breakdown_is_put_candidate():
    events = combine([_alert(95, "top")], [_tbreak(100, "breakdown")], lookback=20)
    assert len(events) == 1
    ev = events[0]
    assert ev.candidate == "put_candidate"
    assert ev.gap_bars == 5


def test_combine_bottom_plus_breakout_is_call_candidate():
    events = combine([_alert(90, "bottom")], [_tbreak(100, "breakout")], lookback=20)
    assert [e.candidate for e in events] == ["call_candidate"]


def test_combine_respects_lookback_window():
    # Alert 25 bars before the break, lookback 20 -> no pairing.
    assert combine([_alert(75, "top")], [_tbreak(100, "breakdown")], lookback=20) == []
    # Alert AFTER the break never pairs.
    assert combine([_alert(105, "top")], [_tbreak(100, "breakdown")], lookback=20) == []


def test_combine_direction_mismatch_does_not_pair():
    assert combine([_alert(95, "bottom")], [_tbreak(100, "breakdown")], lookback=20) == []


def test_combine_picks_most_recent_matching_alert():
    events = combine([_alert(85, "top"), _alert(95, "top")],
                     [_tbreak(100, "breakdown")], lookback=20)
    assert len(events) == 1
    assert events[0].alert.bar_idx == 95


def test_divergence_alerts_smoke_and_threshold():
    bars = random_walk_bars()
    alerts = divergence_alerts(bars, instrument_class="us_equity",
                               min_confidence=0.0)
    assert isinstance(alerts, list)
    assert all(a.direction in ("top", "bottom") for a in alerts)
    assert all(a.level in ("intra_cycle", "inter_cycle", "inter_segment")
               for a in alerts)
    high = divergence_alerts(bars, instrument_class="us_equity",
                             min_confidence=0.9)
    assert len(high) <= len(alerts)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/huhan/code/trading/paired-trading/src && uv run pytest tests/test_alert_chain.py -v`
Expected: FAIL — `ImportError: cannot import name 'ChainEvent' from 'engine.divergence.alert_chain'` (module missing)

- [ ] **Step 3: Implement `src/engine/divergence/alert_chain.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/huhan/code/trading/paired-trading/src && uv run pytest tests/test_alert_chain.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
cd /Users/huhan/code/trading/paired-trading
jj describe -m "feat(alert-chain): divergence alert x tbreak -> put/call candidates

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" && jj new
```

---

### Task 5: Full-pool scan script (`scripts/scan_tbreak_chain.py`)

**Files:**
- Create: `src/scripts/scan_tbreak_chain.py`

- [ ] **Step 1: Implement the script** (no unit test — covered by engine tests; acceptance = real-data run in Step 2)

```python
"""Scan all pools for divergence-alert × trendline-break chain events.

Phase A deliverable: candidate-event lists (per pool, per symbol) for the
post-migration premium-space harness. NO EV claims here.

Usage:
    uv run python scripts/scan_tbreak_chain.py
    uv run python scripts/scan_tbreak_chain.py --pool CN_COMMODITY --since 2021-01-04
    uv run python scripts/scan_tbreak_chain.py -o ../data/review/tbreak_chain_events.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data import bar_loader
from engine.divergence.alert_chain import combine, divergence_alerts
from engine.divergence.tbreak_detector import TBreakDetector

DEFAULT_BARS_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "data" / "review" / "tbreak_chain_events.json"

# Mirrors score_today.py POOLS / POOL_INSTRUMENT_CLASS (2026-06-10).
POOLS: dict[str, list[str]] = {
    "US": ["SPY", "QQQ", "IWM", "DIA", "GLD", "GDX", "XLF", "XLK", "TLT",
           "NVDA", "XLB", "XLE", "XLRE", "XLU"],
    "CN_COMMODITY": [
        "kq_m_shfe_rb", "kq_m_shfe_cu", "kq_m_shfe_au", "kq_m_shfe_ag",
        "kq_m_dce_m", "kq_m_dce_i", "kq_m_dce_j", "kq_m_dce_jm",
        "kq_m_dce_p", "kq_m_dce_y",
        "kq_m_czce_ta", "kq_m_czce_ma", "kq_m_czce_cf", "kq_m_czce_sr",
        "kq_m_ine_sc",
    ],
    "CN_BOND": ["kq_m_cffex_tf", "kq_m_cffex_t", "kq_m_cffex_ts"],
}
POOL_INSTRUMENT_CLASS: dict[str, str] = {
    "US": "us_equity",
    "CN_COMMODITY": "cn_futures",
    "CN_BOND": "cn_bond",
}


def scan_symbol(sym: str, instrument_class: str, bars_dir: Path,
                since: str, lookback: int) -> list[dict] | None:
    bars = bar_loader.load_bars_quant_or_json(sym, "_daily", bars_dir)
    if bars is None or len(bars) < 80:
        return None
    alerts = divergence_alerts(bars, instrument_class=instrument_class)
    tbreaks = TBreakDetector().scan(bars)
    events = combine(alerts, tbreaks, lookback=lookback)
    out = []
    for ev in events:
        ts = ev.tbreak.timestamp
        if str(ts.date()) < since:
            continue
        out.append({
            "symbol": sym,
            "candidate": ev.candidate,
            "break_date": str(ts.date()),
            "break_close": ev.tbreak.features.get("close"),
            "alert_date": str(ev.alert.timestamp.date()),
            "alert_level": ev.alert.level,
            "alert_subtype": ev.alert.subtype,
            "alert_confidence": round(ev.alert.confidence, 3),
            "gap_bars": ev.gap_bars,
            "line": {k: ev.tbreak.features.get(k) for k in (
                "kind", "anchor_idx1", "anchor_price1", "anchor_idx2",
                "anchor_price2", "slope", "line_value", "touches")},
        })
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool", choices=sorted(POOLS), default=None,
                        help="single pool (default: all)")
    parser.add_argument("--since", default="2021-01-04")
    parser.add_argument("--lookback", type=int, default=20)
    parser.add_argument("--bars-dir", type=Path, default=DEFAULT_BARS_DIR)
    parser.add_argument("-o", "--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    pools = {args.pool: POOLS[args.pool]} if args.pool else POOLS
    result: dict[str, dict[str, list[dict]]] = {}
    for pool, symbols in pools.items():
        icls = POOL_INSTRUMENT_CLASS[pool]
        result[pool] = {}
        for sym in symbols:
            events = scan_symbol(sym, icls, args.bars_dir, args.since, args.lookback)
            if events is None:
                print(f"  [skip] {sym}: no/short bars", file=sys.stderr)
                continue
            result[pool][sym] = events

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1, ensure_ascii=False))
    print(f"wrote {args.out}")

    # Sanity summary: events/year per pool+candidate. Spec expectation:
    # single digits to a few tens per symbol-year; 0 everywhere or 100s
    # per symbol-year => parameter or bug suspicion.
    print(f"\n{'pool':14s} {'candidate':16s} {'year':6s} {'n':>4s}")
    for pool, by_sym in result.items():
        counter: Counter[tuple[str, str]] = Counter()
        n_syms = max(1, len(by_sym))
        for sym, events in by_sym.items():
            for ev in events:
                counter[(ev["candidate"], ev["break_date"][:4])] += 1
        for (cand, year), n in sorted(counter.items()):
            print(f"{pool:14s} {cand:16s} {year:6s} {n:4d}  "
                  f"(~{n / n_syms:.1f}/symbol)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Real-data acceptance run**

Run: `cd /Users/huhan/code/trading/paired-trading/src && uv run python scripts/scan_tbreak_chain.py`
Expected:
- JSON written to `src/data/review/tbreak_chain_events.json` (gitignored artifact)
- summary table prints; **sanity band**: roughly 1-40 events per symbol-year overall, put_candidates present in CN_COMMODITY, call_candidates present across pools. 0 everywhere or 100s/symbol-year ⇒ investigate before committing (check buffer/lookback/pivot_n first).
- `[skip]` lines are acceptable for symbols without local daily bars.

- [ ] **Step 3: Run the full test suite (regression)**

Run: `cd /Users/huhan/code/trading/paired-trading/src && uv run pytest -q`
Expected: 504 existing + ~20 new, all passed

- [ ] **Step 4: Commit**

```bash
cd /Users/huhan/code/trading/paired-trading
jj describe -m "feat(scan): full-pool tbreak-chain candidate event scan

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" && jj new
```

---

### Task 6: Codex review, docs touch-up, push

- [ ] **Step 1: Codex pre-flight**

Run: `cd /Users/huhan/code/trading/paired-trading && codex review --base main@origin` (or `--uncommitted` if anything pending)
Expected: fix all P1/P2 findings, re-run until no actionable issues; P3 at discretion.

- [ ] **Step 2: Update STATUS.md (alert-layer note, NOT a lane)**

Add one short block under the current sync section:

```markdown
> **Phase A (2026-06-10)** — Xiao right-side chain machinery landed:
> `trendline.py` + `TBreakDetector` (alert-only, policy_weight=0) +
> `alert_chain.py` (pre-gate divergence alerts × tbreak → put/call
> candidates) + `scan_tbreak_chain.py`. NOT a production lane; no
> baselines; premium-space validation post-migration. Spec:
> `docs/superpowers/specs/2026-06-10-phase-a-tbreak-chain-design.md`.
```

- [ ] **Step 3: Final commit + push**

```bash
cd /Users/huhan/code/trading/paired-trading
jj describe -m "docs(status): Phase A tbreak-chain machinery note

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
jj bookmark move main --to @ && jj git push
jj new
```

---

## Self-Review Notes

- Spec §3 components ↔ Tasks 1/2/4/5; spec §4 defaults all appear as constructor/CLI params; spec §5 tests 1-6 ↔ Task 1 (geometry, causality), Task 2 (buffer, gap, confirm-cancel, policy_weight=0), Task 4 (window/direction mapping). Spec §5 acceptance ↔ Task 5 Step 2-3 and Task 6.
- Type consistency: `TBreakSignal.direction` ∈ {"breakdown","breakout"} used identically in Tasks 2/4/5; `ChainEvent.candidate` ∈ {"put_candidate","call_candidate"}; `fit_trendline(bars, up_to_idx, kind, pivot_n)` signature identical in Tasks 1/2.
- Known accepted caveat (documented in alert_chain docstring + scan output): alert timing uses `candidate_bar_idx` (post-hoc), fine for candidate lists, must be re-derived before any EV work.
- CN index-futures pool ("CN") intentionally omitted from scan pools — no validated interest; add later if Xiao's put pool includes index futures.
