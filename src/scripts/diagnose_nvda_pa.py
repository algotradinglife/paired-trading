"""Diagnose NVDA PABottomDetector failure.

For each signal on NVDA daily bars:
  - Entry/stop/target levels
  - Outcome (stop hit / TP1 hit / TP2 hit / timeout)
  - ATR vs price ratio (stop tightness)
  - Signal quality metrics
  - Weekly context
"""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from engine.divergence.pa_detector import PABottomDetector
from engine.features.macd import macd as compute_macd

BARS_DIR   = Path(__file__).resolve().parents[1] / "data" / "raw"
ATR_PERIOD = 14
MAX_HOLD   = 40
STOP_MULT  = 1.5

def load_bars(sym, suffix="_daily"):
    c = list(BARS_DIR.glob(f"**/{sym}{suffix}.json"))
    if not c: return None
    p = json.loads(c[0].read_text())
    raw = p.get("bars", p) if isinstance(p, dict) else p
    df = pd.DataFrame(raw)
    df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df.sort_values("timestamp").reset_index(drop=True)

def compute_atr(bars, period=ATR_PERIOD):
    hi, lo, pc = bars["high"], bars["low"], bars["close"].shift(1)
    tr = pd.concat([(hi-lo),(hi-pc).abs(),(lo-pc).abs()], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()

def weekly_up_series(bars):
    ts = bars["timestamp"]
    cl = bars["close"].copy()
    cl.index = ts
    wc = cl.resample("W-FRI").last().dropna()
    we = wc.ewm(span=20, adjust=False).mean()
    wu = (wc > we).astype(float)
    daily = wu.reindex(ts, method="ffill")
    daily.index = bars.index
    return daily.fillna(False).astype(bool)

def trace_trade(bars, entry_idx, atr_series):
    """Return detailed dict of what happened."""
    entry = float(bars["close"].iloc[entry_idx])
    av    = float(atr_series.iloc[entry_idx])
    if av <= 0 or not np.isfinite(av):
        return None
    risk  = STOP_MULT * av
    stop  = entry - risk
    tp1   = entry + risk
    tp2   = entry + 2 * risk
    atr_pct = av / entry * 100

    hit_tp1 = False
    outcome = "timeout"
    exit_bar = None
    exit_price = None

    for offset in range(1, MAX_HOLD + 1):
        idx = entry_idx + offset
        if idx >= len(bars):
            idx_fin = len(bars) - 1
            exit_bar, exit_price = idx_fin, float(bars["close"].iloc[idx_fin])
            break
        lo = float(bars["low"].iloc[idx])
        hi = float(bars["high"].iloc[idx])
        cl = float(bars["close"].iloc[idx])
        if not hit_tp1:
            if lo <= stop:
                outcome, exit_bar, exit_price = "stop", idx, stop
                break
            if hi >= tp1:
                hit_tp1 = True
                if hi >= tp2:
                    outcome, exit_bar, exit_price = "tp2", idx, tp2
                    break
        else:
            if lo <= stop:
                outcome, exit_bar, exit_price = "be_stop", idx, stop
                break
            if hi >= tp2:
                outcome, exit_bar, exit_price = "tp2", idx, tp2
                break
            if offset == MAX_HOLD:
                mark = (cl - entry) / risk
                outcome = f"timeout_tp1"
                exit_bar, exit_price = idx, cl
    else:
        idx_fin = min(entry_idx + MAX_HOLD, len(bars) - 1)
        exit_price = float(bars["close"].iloc[idx_fin])
        exit_bar = idx_fin

    r_out = {"stop": -1.0, "tp2": 1.5, "be_stop": 0.0}.get(
        outcome, float(np.clip((exit_price - entry)/risk, -3.0, 3.0))
    )
    return {
        "entry": round(entry, 2),
        "stop": round(stop, 2),
        "tp1":  round(tp1, 2),
        "tp2":  round(tp2, 2),
        "atr":  round(av, 2),
        "atr_pct": round(atr_pct, 1),
        "risk_pct": round(risk/entry*100, 1),
        "outcome": outcome,
        "exit_bar": exit_bar,
        "bars_held": (exit_bar - entry_idx) if exit_bar else MAX_HOLD,
        "r": round(r_out, 3),
    }

def main():
    bars   = load_bars("nvda")
    h_bars = load_bars("nvda", suffix="_60")
    atr    = compute_atr(bars)
    macd_df = compute_macd(bars["close"])
    wu     = weekly_up_series(bars)

    det = PABottomDetector(min_h_legs=2, min_quality=0.3, ema_threshold=0.0, min_gap=10)
    sigs = det.scan(bars, h_bars)

    print(f"NVDA: {len(sigs)} PA signals  ({sum(1 for s in sigs if s.higher_tf_relation=='opposing')} h=opp)")

    CUTOFFS = [
        ("IS",   pd.Timestamp("2022-12-31", tz="UTC")),
        ("OOS1", pd.Timestamp("2023-12-31", tz="UTC")),
        ("OOS2", pd.Timestamp("2024-12-31", tz="UTC")),
    ]
    def period(ts):
        for lbl, cut in CUTOFFS:
            if ts <= cut: return lbl
        return "OOS3"

    records = []
    for sig in sigs:
        td = trace_trade(bars, sig.bar_idx, atr)
        if td is None: continue
        ts = sig.timestamp
        dif = float(macd_df["dif"].iloc[sig.bar_idx])
        records.append({
            "ts": ts.date(),
            "period": period(ts),
            "h_rel": sig.higher_tf_relation,
            "weekly_up": bool(wu.iloc[sig.bar_idx]),
            "dif_pos": dif > 0,
            "conf": round(sig.confidence, 3),
            **{k: sig.features.get(k) for k in ("h_leg_count","bar_quality_bull","selling_climax_score")},
            **td,
        })

    df = pd.DataFrame(records)
    opp = df[df["h_rel"] == "opposing"]
    oos = df[df["period"] != "IS"]
    opp_oos = opp[opp["period"] != "IS"]

    # --- 1. Outcome distribution ---
    print("\n── Outcome breakdown (h=opp, OOS) ──")
    if not opp_oos.empty:
        vc = opp_oos["outcome"].value_counts()
        for k, v in vc.items():
            sub = opp_oos[opp_oos["outcome"] == k]
            print(f"  {k:<14}: n={v:3d}  EV={sub['r'].mean():+.3f}R  avg_held={sub['bars_held'].mean():.0f}bars")
    
    # --- 2. Stop tightness ---
    print("\n── ATR / stop tightness (all signals, OOS) ──")
    for grp_label, grp in [("h=opp", opp_oos), ("all OOS", oos[oos["period"]!="IS"])]:
        if grp.empty: continue
        print(f"  {grp_label}: atr_pct median={grp['atr_pct'].median():.1f}%  "
              f"risk_pct median={grp['risk_pct'].median():.1f}%  "
              f"p75={grp['risk_pct'].quantile(.75):.1f}%")

    # --- 3. Bars-held distribution for stops ---
    print("\n── Stop hits — how fast? (h=opp, OOS) ──")
    stops = opp_oos[opp_oos["outcome"] == "stop"]
    if not stops.empty:
        print(f"  n={len(stops)}  avg bars to stop={stops['bars_held'].mean():.1f}  "
              f"median={stops['bars_held'].median():.0f}  "
              f"<3bars={( stops['bars_held']<=3).mean():.0%}  "
              f"<7bars={(stops['bars_held']<=7).mean():.0%}")

    # --- 4. Signal quality metrics ---
    print("\n── Signal quality: stops vs wins (h=opp, OOS) ──")
    for label, sub in [("stops", stops), ("wins", opp_oos[opp_oos["r"] > 0])]:
        if sub.empty: continue
        print(f"  {label}: conf={sub['conf'].mean():.3f}  "
              f"bar_qual={sub['bar_quality_bull'].mean():.3f}  "
              f"h_legs={sub['h_leg_count'].mean():.1f}  "
              f"climax={sub['selling_climax_score'].mean():.3f}")

    # --- 5. Compare to SPY/GLD (sanity check) ---
    print("\n── Comparison: risk_pct for SPY vs NVDA (h=opp, OOS) ──")
    for sym in ["spy", "gld", "nvda"]:
        b2 = load_bars(sym)
        if b2 is None: continue
        a2  = compute_atr(b2)
        h2  = load_bars(sym, suffix="_60")
        s2  = det.scan(b2, h2)
        rp  = [float(a2.iloc[s.bar_idx]) / float(b2["close"].iloc[s.bar_idx]) * 100 * STOP_MULT
               for s in s2 if s.higher_tf_relation == "opposing" and s.timestamp > pd.Timestamp("2022-12-31", tz="UTC")]
        if rp:
            print(f"  {sym}: median_risk%={np.median(rp):.1f}%  p75={np.percentile(rp,75):.1f}%  p90={np.percentile(rp,90):.1f}%")

    # --- 6. Individual OOS h=opp signals ---
    print("\n── Individual NVDA h=opp OOS signals ──")
    cols = ["ts","period","weekly_up","dif_pos","atr_pct","risk_pct","outcome","bars_held","r","conf"]
    print(opp_oos[cols].to_string(index=False))

if __name__ == "__main__":
    main()
