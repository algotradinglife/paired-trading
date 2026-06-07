"""PA structure classification for US pool symbols.

For each symbol:
  - Detects confirmed pivot H/L sequence → HH/HL/LH/LL labels
  - Classifies current structural phase: BULL / TR / TR_FORMING / BEAR / UNCLEAR
  - Determines structural stop reference:
      BULL  → most recent confirmed HL (highest recent low)
      TR    → TR floor (lowest recent pivot low) - 1% buffer
      BEAR  → n/a (no long entry)
  - Reports current close position within structure
"""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from engine.features.macd import macd as compute_macd

BARS_DIR  = Path(__file__).resolve().parents[1] / "data" / "raw"
US_SYMBOLS = ["spy","qqq","iwm","gld","tlt","nvda","dia","gdx","xlf","xlk"]
PIVOT_N    = 5   # bars each side for pivot confirmation
SEQ_WINDOW = 10  # recent pivots used for phase classification
TR_BUFFER  = 0.01

def load_bars(sym, suffix="_daily"):
    c = list(BARS_DIR.glob(f"**/{sym}{suffix}.json"))
    if not c: return None
    p = json.loads(c[0].read_text())
    raw = p.get("bars", p) if isinstance(p, dict) else p
    df = pd.DataFrame(raw)
    df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df.sort_values("timestamp").reset_index(drop=True)

def find_pivots_full(bars, n=PIVOT_N):
    """Full lookahead pivots — for current structure analysis only."""
    hi_arr = bars["high"].values
    lo_arr = bars["low"].values
    ph, pl = [], []
    for i in range(n, len(bars) - n):
        h = hi_arr[i]
        l = lo_arr[i]
        if h == hi_arr[i-n:i+n+1].max() and h > hi_arr[i-1] and h > hi_arr[i+1]:
            ph.append({"bar": i, "ts": bars["timestamp"].iloc[i].date(), "val": h})
        if l == lo_arr[i-n:i+n+1].min() and l < lo_arr[i-1] and l < lo_arr[i+1]:
            pl.append({"bar": i, "ts": bars["timestamp"].iloc[i].date(), "val": l})
    return ph, pl

def label_sequence(ph, pl):
    events = [{"bar": e["bar"], "ts": e["ts"], "val": e["val"], "kind": "H"} for e in ph] + \
             [{"bar": e["bar"], "ts": e["ts"], "val": e["val"], "kind": "L"} for e in pl]
    events.sort(key=lambda x: x["bar"])
    prev_h = prev_l = None
    result = []
    for e in events:
        if e["kind"] == "H":
            lbl = ("HH" if prev_h is None else ("HH" if e["val"] > prev_h else "LH"))
            prev_h = e["val"]
        else:
            lbl = ("L"  if prev_l is None else ("HL" if e["val"] > prev_l else "LL"))
            if prev_l is None: lbl = "L"
            prev_l = e["val"]
        result.append({**e, "label": lbl})
    return result

def classify_phase(seq, window=SEQ_WINDOW):
    recent = seq[-window:]
    hh = sum(1 for e in recent if e["label"] == "HH")
    hl = sum(1 for e in recent if e["label"] == "HL")
    lh = sum(1 for e in recent if e["label"] == "LH")
    ll = sum(1 for e in recent if e["label"] == "LL")
    if hh >= 2 and hl >= 2 and ll == 0 and lh <= 1:
        return "BULL"
    if lh >= 2 and ll >= 2 and hh == 0 and hl <= 1:
        return "BEAR"
    if lh >= 1 and hl >= 1 and hh == 0 and ll == 0:
        return "TR"
    if (hh >= 1 and lh >= 1) or (hl >= 1 and ll >= 1):
        return "TR_FORMING"
    return "UNCLEAR"

def structural_info(seq, phase, cur_close, window=12):
    recent = seq[-window:]
    highs = [e["val"] for e in recent if e["kind"] == "H"]
    lows  = [e["val"] for e in recent if e["kind"] == "L"]
    if not highs or not lows:
        return None, None, None, None

    tr_top = max(highs)
    tr_bot = min(lows)

    if phase == "BULL":
        # structural stop = most recent HL (latest pivot low that's higher than prior low)
        hl_events = [e for e in recent if e["label"] in ("HL", "L")]
        struct_stop = (max(e["val"] for e in hl_events) * (1 - TR_BUFFER)
                       if hl_events else tr_bot * (1 - TR_BUFFER))
    elif phase in ("TR", "TR_FORMING"):
        struct_stop = tr_bot * (1 - TR_BUFFER)
    else:  # BEAR or UNCLEAR
        struct_stop = None

    pos_pct = (cur_close - tr_bot) / (tr_top - tr_bot) * 100 if tr_top != tr_bot else 50
    return tr_top, tr_bot, struct_stop, pos_pct

def main():
    print(f"\n{'='*95}")
    print("US Pool — PA Structure Classification")
    print(f"{'='*95}")
    hdr = (f"{'Sym':<6} {'Phase':<12} {'TR top':>8} {'TR bot':>8} "
           f"{'Close':>8} {'Pos%':>6} {'Struct stop':>12} {'Stop dist':>10} {'Always-In':>10}")
    print(hdr)
    print("-" * 95)

    for sym in US_SYMBOLS:
        bars = load_bars(sym)
        if bars is None or len(bars) < 60:
            print(f"{sym:<6} [NO DATA]")
            continue

        ph, pl = find_pivots_full(bars)
        seq    = label_sequence(ph, pl)
        phase  = classify_phase(seq)
        cur    = float(bars["close"].iloc[-1])
        tr_top, tr_bot, sstop, pos_pct = structural_info(seq, phase, cur)

        ai = "Long" if phase == "BULL" else ("Short" if phase == "BEAR" else "—")
        stop_dist = f"{(cur-sstop)/cur*100:+.1f}%" if sstop else "n/a"
        top_s  = f"{tr_top:.1f}" if tr_top else "—"
        bot_s  = f"{tr_bot:.1f}" if tr_bot else "—"
        pos_s  = f"{pos_pct:.0f}%" if pos_pct is not None else "—"
        stop_s = f"{sstop:.1f}" if sstop else "n/a"

        print(f"{sym:<6} {phase:<12} {top_s:>8} {bot_s:>8} "
              f"{cur:>8.1f} {pos_s:>6} {stop_s:>12} {stop_dist:>10} {ai:>10}")

    print()
    # Per-symbol last 8 pivot labels
    print("Recent pivot sequence (last 8 pivots per symbol):")
    for sym in US_SYMBOLS:
        bars = load_bars(sym)
        if bars is None: continue
        ph, pl = find_pivots_full(bars)
        seq    = label_sequence(ph, pl)
        labels = " ".join(f"{e['label']}({e['val']:.0f})" for e in seq[-8:])
        print(f"  {sym:<6}: {labels}")

if __name__ == "__main__":
    main()
