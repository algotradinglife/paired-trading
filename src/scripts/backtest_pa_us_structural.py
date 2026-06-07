"""K=3 walk-forward: ATR stop vs Structural stop + Position Management.

Three-layer framework:
  Layer 1 — PA structure  : phase detection (BULL/TR/BEAR) at signal time
  Layer 2 — Tactical      : structural stop (TR floor / recent HL)
  Layer 3 — Survival      : fixed-risk position sizing + phase allocation + drawdown guard

Position management rules:
  - BASE_RISK = 1% per trade (of account equity)
  - Phase multiplier: BULL=1.0, TR/TR_FORMING=0.5, BEAR=skip, UNCLEAR=skip
  - Consecutive stop guard: 3+ consecutive stops → halve risk until next win
  - Structural stop sets position size: size = (equity × adjusted_risk%) / stop_distance

Comparison columns per K=3 fold:
  ATR stop  : original 1.5×ATR, fixed position (no sizing)
  Struct    : structural stop, variable position, phase filter
"""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from engine.divergence.pa_detector import PABottomDetector, PASignal
from engine.features.macd import macd as compute_macd

BARS_DIR   = Path(__file__).resolve().parents[1] / "data" / "raw"
US_SYMBOLS = ["spy","qqq","iwm","gld","tlt","nvda","dia","gdx","xlf","xlk"]
PIVOT_N    = 5
MAX_HOLD   = 40
MIN_GAP    = 10
STOP_MULT  = 1.5   # for ATR baseline
STRUCT_BUF = 0.01  # 1% below pivot floor
LOOKBACK   = 40    # bars to look back for structural stop
BASE_RISK  = 0.01  # 1% of equity per trade
CONSEC_THRESH = 3  # consecutive stops before halving risk

CUTOFF_IS   = pd.Timestamp("2022-12-31", tz="UTC")
CUTOFF_OOS1 = pd.Timestamp("2023-12-31", tz="UTC")
CUTOFF_OOS2 = pd.Timestamp("2024-12-31", tz="UTC")

# ── data ─────────────────────────────────────────────────────────────────

def load_bars(sym, suffix="_daily"):
    c = list(BARS_DIR.glob(f"**/{sym}{suffix}.json"))
    if not c: return None
    p = json.loads(c[0].read_text())
    raw = p.get("bars", p) if isinstance(p, dict) else p
    df = pd.DataFrame(raw)
    df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df.sort_values("timestamp").reset_index(drop=True)

def compute_atr(bars, period=14):
    hi, lo, pc = bars["high"], bars["low"], bars["close"].shift(1)
    tr = pd.concat([(hi-lo),(hi-pc).abs(),(lo-pc).abs()], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()

# ── pivot infrastructure (real-time, no right-side lookahead in backtest) ─

def precompute_confirmed_pivots(bars, n=PIVOT_N):
    hi = bars["high"].values
    lo = bars["low"].values
    ph, pl = [], []
    for i in range(n, len(bars) - n):
        if hi[i] == hi[i-n:i+n+1].max() and hi[i] > hi[i-1] and hi[i] > hi[i+1]:
            ph.append({"bar": i, "confirmed_at": i+n, "val": float(hi[i])})
        if lo[i] == lo[i-n:i+n+1].min() and lo[i] < lo[i-1] and lo[i] < lo[i+1]:
            pl.append({"bar": i, "confirmed_at": i+n, "val": float(lo[i])})
    return ph, pl

def phase_and_stop_at(signal_bar, ph, pl, entry):
    """Return (phase, structural_stop) available at signal_bar."""
    avail_h = [p for p in ph if p["confirmed_at"] <= signal_bar]
    avail_l = [p for p in pl if p["confirmed_at"] <= signal_bar]
    if len(avail_h) < 2 or len(avail_l) < 2:
        return "UNCLEAR", None

    # Build recent sequence for phase classification
    events = [{"bar": p["bar"], "val": p["val"], "kind": "H"} for p in avail_h[-8:]] + \
             [{"bar": p["bar"], "val": p["val"], "kind": "L"} for p in avail_l[-8:]]
    events.sort(key=lambda x: x["bar"])
    recent = events[-10:]  # last 10 mixed pivots

    prev_h = prev_l = None
    hh = hl = lh = ll = 0
    for e in recent:
        if e["kind"] == "H":
            if prev_h is not None:
                if e["val"] > prev_h: hh += 1
                else: lh += 1
            prev_h = e["val"]
        else:
            if prev_l is not None:
                if e["val"] > prev_l: hl += 1
                else: ll += 1
            prev_l = e["val"]

    if hh >= 2 and hl >= 2 and ll == 0 and lh <= 1:
        phase = "BULL"
    elif lh >= 2 and ll >= 2 and hh == 0 and hl <= 1:
        phase = "BEAR"
    elif lh >= 1 and hl >= 1 and hh == 0 and ll == 0:
        phase = "TR"
    elif (hh >= 1 and lh >= 1) or (hl >= 1 and ll >= 1):
        phase = "TR_FORMING"
    else:
        phase = "UNCLEAR"

    # Structural stop: lowest confirmed pivot low in lookback window
    recent_l = [p for p in avail_l if signal_bar - p["bar"] <= LOOKBACK]
    if not recent_l:
        recent_l = avail_l[-3:] if len(avail_l) >= 3 else avail_l
    if not recent_l:
        return phase, None
    floor = min(p["val"] for p in recent_l)
    sstop = floor * (1 - STRUCT_BUF)
    if sstop >= entry:
        return phase, None
    return phase, sstop

# ── trade simulation ──────────────────────────────────────────────────────

def sim_atr(bars, entry_idx, atr_series):
    if entry_idx + 1 >= len(bars): return None
    entry = float(bars["close"].iloc[entry_idx])
    av = float(atr_series.iloc[entry_idx])
    if av <= 0 or not np.isfinite(av): return None
    risk = STOP_MULT * av
    stop = entry - risk
    tp1  = entry + risk
    tp2  = entry + 2 * risk
    hit_tp1 = False
    for offset in range(1, MAX_HOLD + 1):
        idx = entry_idx + offset
        if idx >= len(bars): break
        lo = float(bars["low"].iloc[idx])
        hi = float(bars["high"].iloc[idx])
        cl = float(bars["close"].iloc[idx])
        if not hit_tp1:
            if lo <= stop: return -1.0
            if hi >= tp1:
                hit_tp1 = True
                if hi >= tp2: return 1.5
        else:
            if lo <= stop: return 0.0
            if hi >= tp2: return 1.5
            if offset == MAX_HOLD:
                return 0.5 + 0.5*float(np.clip((cl-entry)/risk, -3, 3))
    idx_f = min(entry_idx+MAX_HOLD, len(bars)-1)
    return float(np.clip((float(bars["close"].iloc[idx_f])-entry)/av/STOP_MULT, -3, 3))

def sim_structural(bars, entry_idx, sstop):
    if entry_idx + 1 >= len(bars) or sstop is None: return None, None
    entry = float(bars["close"].iloc[entry_idx])
    if sstop >= entry: return None, None
    risk = entry - sstop
    stop_dist_pct = risk / entry
    tp1  = entry + risk
    tp2  = entry + 2 * risk
    hit_tp1 = False
    for offset in range(1, MAX_HOLD + 1):
        idx = entry_idx + offset
        if idx >= len(bars): break
        lo = float(bars["low"].iloc[idx])
        hi = float(bars["high"].iloc[idx])
        cl = float(bars["close"].iloc[idx])
        if not hit_tp1:
            if lo <= sstop: return -1.0, stop_dist_pct
            if hi >= tp1:
                hit_tp1 = True
                if hi >= tp2: return 1.5, stop_dist_pct
        else:
            if lo <= sstop: return 0.0, stop_dist_pct
            if hi >= tp2: return 1.5, stop_dist_pct
            if offset == MAX_HOLD:
                mark = (cl-entry)/risk
                return 0.5+0.5*float(np.clip(mark,-3,3)), stop_dist_pct
    idx_f = min(entry_idx+MAX_HOLD, len(bars)-1)
    mark = (float(bars["close"].iloc[idx_f])-entry)/risk
    return float(np.clip(mark,-3,3)), stop_dist_pct

# ── account simulation with position management ───────────────────────────

def account_sim(records_oos):
    """Simulate account equity with 3-layer position management."""
    equity = 100.0
    consec_stops = 0
    curve = []
    for rec in sorted(records_oos, key=lambda r: r["ts"]):
        phase = rec["phase"]
        # Phase allocation
        if phase in ("BEAR", "UNCLEAR"):
            continue
        phase_mult = 1.0 if phase == "BULL" else 0.5  # TR/TR_FORMING = half

        # Consecutive stop guard
        consec_mult = 0.5 if consec_stops >= CONSEC_THRESH else 1.0
        adj_risk = BASE_RISK * phase_mult * consec_mult

        r = rec["r_struct"]
        if r is None:
            continue
        pnl_pct = adj_risk * r  # e.g. 1% × 1.5 = +1.5% for a win
        equity *= (1 + pnl_pct)

        if r <= -0.9:  # stop hit
            consec_stops += 1
        else:
            consec_stops = 0

        curve.append({
            "ts": rec["ts"],
            "equity": round(equity, 4),
            "r": r,
            "phase": phase,
            "adj_risk_pct": round(adj_risk * 100, 2),
            "consec_stops": consec_stops,
        })
    return curve

# ── main ─────────────────────────────────────────────────────────────────

def main():
    det = PABottomDetector(min_h_legs=2, min_quality=0.3, ema_threshold=0.0, min_gap=MIN_GAP)

    all_records: list[dict] = []

    for sym in US_SYMBOLS:
        bars   = load_bars(sym)
        if bars is None or len(bars) < 100: continue
        h_bars = load_bars(sym, suffix="_60")
        atr    = compute_atr(bars)
        ph, pl = precompute_confirmed_pivots(bars)

        sigs = det.scan(bars, h_bars)
        opp_sigs = [s for s in sigs if s.higher_tf_relation == "opposing"]

        for sig in opp_sigs:
            r_a = sim_atr(bars, sig.bar_idx, atr)
            if r_a is None: continue

            entry = float(bars["close"].iloc[sig.bar_idx])
            phase, sstop = phase_and_stop_at(sig.bar_idx, ph, pl, entry)
            r_s, stop_pct = sim_structural(bars, sig.bar_idx, sstop)

            ts = sig.timestamp
            period = ("IS"   if ts <= CUTOFF_IS   else
                      "OOS1" if ts <= CUTOFF_OOS1 else
                      "OOS2" if ts <= CUTOFF_OOS2 else "OOS3")
            dif_val = float(compute_macd(bars["close"])["dif"].iloc[sig.bar_idx])

            all_records.append({
                "sym": sym, "ts": ts, "period": period,
                "h_rel": sig.higher_tf_relation,
                "dif_pos": dif_val > 0,
                "phase": phase,
                "r_atr": r_a,
                "r_struct": r_s,
                "sstop_pct": round(stop_pct * 100, 1) if stop_pct else None,
                "atr_pct": round(float(atr.iloc[sig.bar_idx]) / entry * 100, 1),
            })

        print(f"  {sym}: {len(opp_sigs)} h=opp signals")

    df = pd.DataFrame(all_records)
    oos = df[df["period"] != "IS"]
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    oos = df[df["period"] != "IS"]

    def fold_row(sub, col):
        if sub.empty: return "n=0"
        parts = []
        for p, lbl in [("OOS1","F1"),("OOS2","F2"),("OOS3","F3")]:
            g = sub[sub["period"] == p][col].dropna()
            parts.append(f"{lbl}={g.mean():+.3f}R(n={len(g)})" if len(g) else f"{lbl}=—")
        return "  ".join(parts)

    print(f"\n{'='*100}")
    print("ATR stop vs Structural stop — h=opposing K=3 (OOS only)")
    print(f"{'='*100}")

    for label, sub in [
        ("ALL h=opp",          oos),
        ("DIF<0 h=opp",        oos[~oos["dif_pos"]]),
        ("DIF>0 h=opp",        oos[oos["dif_pos"]]),
        ("BULL phase",         oos[oos["phase"]=="BULL"]),
        ("TR phase",           oos[oos["phase"].isin(["TR","TR_FORMING"])]),
    ]:
        ra = sub["r_atr"].dropna()
        rs = sub["r_struct"].dropna()
        print(f"\n  [{label}]  n_atr={len(ra)}  n_struct={len(rs)}")
        print(f"    ATR    EV={ra.mean():+.3f}R  {fold_row(sub,'r_atr')}")
        print(f"    Struct EV={rs.mean():+.3f}R  {fold_row(sub,'r_struct')}")
        if not sub.empty:
            sp = sub["sstop_pct"].dropna()
            ap = sub["atr_pct"].dropna() * STOP_MULT
            print(f"    Stop dist: ATR={ap.median():.1f}%(med)  Struct={sp.median():.1f}%(med)")

    # Phase distribution
    print(f"\n── Phase distribution (OOS h=opp) ──")
    for ph_lbl in ["BULL","TR","TR_FORMING","BEAR","UNCLEAR"]:
        sub = oos[oos["phase"]==ph_lbl]
        if sub.empty: continue
        rs = sub["r_struct"].dropna()
        print(f"  {ph_lbl:<14}: n={len(sub):3d}  struct_EV={rs.mean():+.3f}R  "
              f"atr_EV={sub['r_atr'].dropna().mean():+.3f}R")

    # Account simulation (structural + position management, OOS)
    print(f"\n── Account equity simulation (OOS, structural stop + PM) ──")
    print(f"  Rules: {BASE_RISK*100:.0f}% risk/trade | TR=half | {CONSEC_THRESH} consec stops → halve")
    oos_records = [r for r in all_records if r["period"] != "IS"]
    curve = account_sim(oos_records)
    if curve:
        final_eq = curve[-1]["equity"]
        returns  = pd.Series([c["equity"] for c in curve]).pct_change().dropna()
        max_eq   = pd.Series([c["equity"] for c in curve]).cummax()
        dd       = ((pd.Series([c["equity"] for c in curve]) - max_eq) / max_eq).min()
        print(f"  Final equity: {final_eq:.1f}  (started 100)")
        print(f"  Total return: {(final_eq-100):.1f}%  MaxDD: {dd*100:.1f}%")
        # Per-fold
        for p, lbl in [("OOS1","F1"),("OOS2","F2"),("OOS3","F3")]:
            fc = [c for c in curve if any(r["ts"].strftime("%Y") in
                  ({"OOS1":"2023","OOS2":"2024","OOS3":"2025"}[p] if p!="OOS3" else "2025") 
                  for r in [{"ts":c["ts"]}])]
            sub_r = [c["r"] for c in curve if
                     c["ts"] <= {"OOS1":CUTOFF_OOS1,"OOS2":CUTOFF_OOS2}.get(p, pd.Timestamp("2099",tz="UTC")) and
                     c["ts"] > {"OOS1":CUTOFF_IS,"OOS2":CUTOFF_OOS1}.get(p, CUTOFF_OOS2)]
            if sub_r:
                print(f"  {lbl}: n={len(sub_r)}  avg_R={np.mean(sub_r):+.3f}  "
                      f"hit={(np.array(sub_r)>0).mean():.0%}")

    print(f"\nSaved to /tmp/pa_us_structural.csv")
    df.to_csv("/tmp/pa_us_structural.csv", index=False)

if __name__ == "__main__":
    main()
