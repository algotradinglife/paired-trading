"""PA structure analysis for NVDA daily bars.

1. Pivot swing detection → HH/HL/LH/LL sequence
2. Structural phase classification: bull trend / TR / bear trend
3. If TR: mark range bounds
4. Overlay DIF>0 (Context A) signals on TR structure
"""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from engine.features.macd import macd as compute_macd, ema

BARS_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

# ── helpers ────────────────────────────────────────────────────────────────

def load_bars(sym, suffix="_daily"):
    c = list(BARS_DIR.glob(f"**/{sym}{suffix}.json"))
    if not c: return None
    p = json.loads(c[0].read_text())
    raw = p.get("bars", p) if isinstance(p, dict) else p
    df = pd.DataFrame(raw)
    df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df.sort_values("timestamp").reset_index(drop=True)

def find_pivots(bars, n=5):
    """N-bar pivot highs and lows (analysis only; uses right-side lookahead)."""
    ph, pl = [], []
    hi_arr = bars["high"].values
    lo_arr = bars["low"].values
    for i in range(n, len(bars) - n):
        window_h = hi_arr[i-n:i+n+1]
        window_l = lo_arr[i-n:i+n+1]
        if hi_arr[i] == window_h.max() and hi_arr[i] > hi_arr[i-1] and hi_arr[i] > hi_arr[i+1]:
            ph.append((i, bars["timestamp"].iloc[i], float(hi_arr[i])))
        if lo_arr[i] == window_l.min() and lo_arr[i] < lo_arr[i-1] and lo_arr[i] < lo_arr[i+1]:
            pl.append((i, bars["timestamp"].iloc[i], float(lo_arr[i])))
    return ph, pl

def label_sequence(ph, pl):
    """Merge pivot highs and lows into chronological sequence; label HH/LH/HL/LL."""
    events = [(idx, ts, val, "H") for idx, ts, val in ph] + \
             [(idx, ts, val, "L") for idx, ts, val in pl]
    events.sort(key=lambda x: x[0])

    prev_h = prev_l = None
    result = []
    for idx, ts, val, kind in events:
        if kind == "H":
            if prev_h is None:
                label = "H"
            else:
                label = "HH" if val > prev_h else "LH"
            prev_h = val
        else:
            if prev_l is None:
                label = "L"
            else:
                label = "HL" if val > prev_l else "LL"
            prev_l = val
        result.append({"idx": idx, "ts": ts.date(), "val": round(val, 2), "kind": kind, "label": label})
    return result

def classify_phase(seq, window=8):
    """Classify recent structural phase from the last `window` swing points."""
    recent = seq[-window:]
    hh = sum(1 for e in recent if e["label"] == "HH")
    hl = sum(1 for e in recent if e["label"] == "HL")
    lh = sum(1 for e in recent if e["label"] == "LH")
    ll = sum(1 for e in recent if e["label"] == "LL")

    # strict bull: HH+HL dominant, no LL
    # strict bear: LH+LL dominant, no HH
    # TR: mix of LH and HL without new extremes
    if hh >= 2 and hl >= 2 and ll == 0:
        return "BULL"
    if lh >= 2 and ll >= 2 and hh == 0:
        return "BEAR"
    if lh >= 1 and hl >= 1 and hh == 0 and ll == 0:
        return "TR"
    if hh >= 1 and lh >= 1 and hl >= 1:
        return "TR_FORMING"  # mixed: potential transition
    return "UNCLEAR"

def detect_tr_bounds(seq, window=10):
    """Find TR ceiling and floor from the most recent swing window."""
    recent = seq[-window:]
    highs = [e["val"] for e in recent if e["kind"] == "H"]
    lows  = [e["val"] for e in recent if e["kind"] == "L"]
    if not highs or not lows:
        return None, None
    return max(highs), min(lows)

def context_a_signals(bars, macd_df):
    """Simple DIF>0 + price below EMA20 daily pullback (Context A proxy)."""
    e20 = ema(bars["close"], 20)
    e60 = ema(bars["close"], 60)
    signals = []
    rh = bars["high"].rolling(20).max()  # 20-bar rolling high
    for i in range(60, len(bars)):
        dif = float(macd_df["dif"].iloc[i])
        if dif <= 0:
            continue
        cl   = float(bars["close"].iloc[i])
        e20v = float(e20.iloc[i])
        e60v = float(e60.iloc[i])
        rhv  = float(rh.iloc[i])
        if cl >= e20v:
            continue  # must be below EMA20
        if cl < e60v * 0.97:
            continue  # must not be too far below EMA60
        pb = (rhv - cl) / rhv if rhv > 0 else 0
        if pb < 0.03 or pb > 0.12:
            continue  # pullback 3-12%
        signals.append({
            "idx": i,
            "ts":  bars["timestamp"].iloc[i].date(),
            "close": round(cl, 2),
            "pullback_pct": round(pb * 100, 1),
            "dif": round(dif, 4),
        })
    # deduplicate: keep first in any 10-bar window
    out, last = [], -99
    for s in signals:
        if s["idx"] - last >= 10:
            out.append(s)
            last = s["idx"]
    return out

# ── main ───────────────────────────────────────────────────────────────────

def main():
    bars = load_bars("nvda")
    macd_df = compute_macd(bars["close"])

    ph, pl = find_pivots(bars, n=5)
    seq    = label_sequence(ph, pl)

    # ── 1. Print last 30 swing points ─────────────────────────────────────
    print("NVDA Daily — Recent Swing Sequence (last 30 pivots)")
    print(f"{'Date':<12} {'Type':<4} {'Label':<6} {'Price':>8}")
    print("-" * 35)
    for e in seq[-30:]:
        arrow = "↑" if e["kind"] == "H" else "↓"
        print(f"{str(e['ts']):<12} {arrow:<4} {e['label']:<6} {e['val']:>8.2f}")

    # ── 2. Phase classification ────────────────────────────────────────────
    phase = classify_phase(seq, window=8)
    print(f"\nStructural phase (last 8 pivots): {phase}")

    # Breakdown
    recent8 = seq[-8:]
    counts = {lbl: sum(1 for e in recent8 if e["label"] == lbl)
              for lbl in ["HH","HL","LH","LL"]}
    print(f"  HH={counts['HH']} HL={counts['HL']} LH={counts['LH']} LL={counts['LL']}")

    # ── 3. TR bounds ───────────────────────────────────────────────────────
    tr_top, tr_bot = detect_tr_bounds(seq, window=12)
    print(f"\nTR bounds (last 12 pivots):")
    print(f"  Ceiling : {tr_top:.2f}")
    print(f"  Floor   : {tr_bot:.2f}")
    rng_pct = (tr_top - tr_bot) / tr_bot * 100
    print(f"  Range   : {rng_pct:.1f}%")

    cur_close = float(bars["close"].iloc[-1])
    cur_ts    = bars["timestamp"].iloc[-1].date()
    pos_in_tr = (cur_close - tr_bot) / (tr_top - tr_bot) * 100
    print(f"  Current close ({cur_ts}): {cur_close:.2f}  → {pos_in_tr:.0f}% of range")

    # ── 4. Context A signals — last 24 months ─────────────────────────────
    ctx_a = context_a_signals(bars, macd_df)
    cutoff = pd.Timestamp("2024-01-01", tz="UTC")
    recent_a = [s for s in ctx_a
                if bars["timestamp"].iloc[s["idx"]] >= cutoff]

    print(f"\nContext A (DIF>0 pullback) signals since 2024-01-01: n={len(recent_a)}")
    print(f"{'Date':<12} {'Close':>8} {'PB%':>6} {'DIF':>8} {'vs TR bot':>12} {'zone':>12}")
    print("-" * 65)
    for s in recent_a:
        dist_from_bot = (s["close"] - tr_bot) / tr_bot * 100
        zone_pct      = (s["close"] - tr_bot) / (tr_top - tr_bot) * 100 if tr_top != tr_bot else 0
        zone          = "BOTTOM <25%" if zone_pct < 25 else ("MID" if zone_pct < 75 else "TOP >75%")
        print(f"{str(s['ts']):<12} {s['close']:>8.2f} {s['pullback_pct']:>5.1f}% "
              f"{s['dif']:>8.4f} {dist_from_bot:>+10.1f}% {zone:>12}")

    # ── 5. Check: do Context A signals cluster near TR bottom? ─────────────
    if recent_a:
        bot_signals = [s for s in recent_a
                       if (s["close"] - tr_bot)/(tr_top - tr_bot)*100 < 33]
        print(f"\n  Signals in bottom third of TR (<33% of range): "
              f"{len(bot_signals)}/{len(recent_a)} = {len(bot_signals)/len(recent_a):.0%}")

    # ── 6. Key TR levels for stop reference ───────────────────────────────
    print(f"\nStructural stop reference:")
    print(f"  TR floor (invalidation below): {tr_bot:.2f}  ({(cur_close-tr_bot)/cur_close*100:.1f}% below current)")
    print(f"  TR ceiling (target):           {tr_top:.2f}  ({(tr_top-cur_close)/cur_close*100:.1f}% above current)")

if __name__ == "__main__":
    main()
