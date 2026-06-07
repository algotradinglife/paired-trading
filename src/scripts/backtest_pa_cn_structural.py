"""K=3 walk-forward: ATR stop vs Structural stop for CN_METAL PA H2 signals.

Mirrors backtest_pa_us_structural.py but for CN_METAL pool.
h=opposing filter applied throughout (K=3 validated baseline).

Symbols: kq_m_shfe_cu, kq_m_shfe_au, kq_m_shfe_ag, kq_m_ine_sc
Daily suffix: _daily   60min suffix: _60
"""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from data import bar_loader
from engine.divergence.pa_detector import PABottomDetector, PASignal
from engine.divergence.pa_structure import PAStructureDetector
from engine.features.macd import macd as compute_macd

BARS_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
CN_METAL = ["kq_m_shfe_cu","kq_m_shfe_au","kq_m_shfe_ag","kq_m_ine_sc"]
MAX_HOLD  = 40
MIN_GAP   = 5
STOP_MULT = 1.5
STRUCT_BUF = 0.01
LOOKBACK   = 40

CUTOFF_IS   = pd.Timestamp("2022-12-31", tz="UTC")
CUTOFF_OOS1 = pd.Timestamp("2023-12-31", tz="UTC")
CUTOFF_OOS2 = pd.Timestamp("2024-12-31", tz="UTC")

def load_bars(sym, suffix="_daily"):
    return bar_loader.load_bars_quant_or_json(sym, suffix, BARS_DIR)

def compute_atr(bars, period=14):
    hi,lo,pc = bars["high"],bars["low"],bars["close"].shift(1)
    tr = pd.concat([(hi-lo),(hi-pc).abs(),(lo-pc).abs()],axis=1).max(axis=1)
    return tr.ewm(span=period,adjust=False).mean()

def sim_atr(bars, idx, atr):
    entry = float(bars["close"].iloc[idx])
    av    = float(atr.iloc[idx])
    if av<=0 or not np.isfinite(av): return None
    risk=STOP_MULT*av; stop=entry-risk; tp1=entry+risk; tp2=entry+2*risk
    hit1=False
    for off in range(1,MAX_HOLD+1):
        i=idx+off
        if i>=len(bars): break
        lo=float(bars["low"].iloc[i]); hi=float(bars["high"].iloc[i]); cl=float(bars["close"].iloc[i])
        if not hit1:
            if lo<=stop: return -1.0
            if hi>=tp1:
                hit1=True
                if hi>=tp2: return 1.5
        else:
            if lo<=stop: return 0.0
            if hi>=tp2: return 1.5
            if off==MAX_HOLD:
                return 0.5+0.5*float(np.clip((cl-entry)/risk,-3,3))
    f=min(idx+MAX_HOLD,len(bars)-1)
    return float(np.clip((float(bars["close"].iloc[f])-entry)/av/STOP_MULT,-3,3))

def sim_struct(bars, idx, sstop):
    if sstop is None: return None,None
    entry=float(bars["close"].iloc[idx])
    if sstop>=entry: return None,None
    risk=entry-sstop; sdp=risk/entry; tp1=entry+risk; tp2=entry+2*risk
    hit1=False
    for off in range(1,MAX_HOLD+1):
        i=idx+off
        if i>=len(bars): break
        lo=float(bars["low"].iloc[i]); hi=float(bars["high"].iloc[i]); cl=float(bars["close"].iloc[i])
        if not hit1:
            if lo<=sstop: return -1.0,sdp
            if hi>=tp1:
                hit1=True
                if hi>=tp2: return 1.5,sdp
        else:
            if lo<=sstop: return 0.0,sdp
            if hi>=tp2: return 1.5,sdp
            if off==MAX_HOLD:
                return 0.5+0.5*float(np.clip((cl-entry)/risk,-3,3)),sdp
    f=min(idx+MAX_HOLD,len(bars)-1)
    return float(np.clip((float(bars["close"].iloc[f])-entry)/risk,-3,3)),sdp

def main():
    det        = PABottomDetector(min_h_legs=2,min_quality=0.3,ema_threshold=0.0,min_gap=MIN_GAP)
    struct_det = PAStructureDetector()

    records=[]
    for sym in CN_METAL:
        bars   = load_bars(sym)
        if bars is None or len(bars)<100: print(f"  [SKIP] {sym}"); continue
        h_bars = load_bars(sym,suffix="_60")
        atr    = compute_atr(bars)
        macd_df = compute_macd(bars["close"])
        sigs   = [s for s in det.scan(bars,h_bars) if s.higher_tf_relation=="opposing"]
        print(f"  {sym}: {len(sigs)} h=opp signals")

        for sig in sigs:
            ra = sim_atr(bars,sig.bar_idx,atr)
            if ra is None: continue
            entry  = float(bars["close"].iloc[sig.bar_idx])
            struct = struct_det.detect(bars,up_to_idx=sig.bar_idx)
            rs,sdp = sim_struct(bars,sig.bar_idx,struct.structural_stop)

            ts=sig.timestamp
            period=("IS" if ts<=CUTOFF_IS else "OOS1" if ts<=CUTOFF_OOS1 else "OOS2" if ts<=CUTOFF_OOS2 else "OOS3")
            dif=float(macd_df["dif"].iloc[sig.bar_idx])
            records.append({
                "sym":sym,"ts":ts,"period":period,
                "dif_pos":dif>0,"phase":struct.phase,
                "r_atr":ra,"r_struct":rs,
                "sstop_pct":round(sdp*100,1) if sdp else None,
                "atr_pct":round(float(atr.iloc[sig.bar_idx])/entry*100,1),
            })

    df=pd.DataFrame(records)
    oos=df[df["period"]!="IS"]

    def fold(sub,col):
        if sub.empty: return "n=0"
        parts=[]
        for p,lbl in [("OOS1","F1"),("OOS2","F2"),("OOS3","F3")]:
            g=sub[sub["period"]==p][col].dropna()
            parts.append(f"{lbl}={g.mean():+.3f}R(n={len(g)})" if len(g) else f"{lbl}=—")
        return "  ".join(parts)

    print(f"\n{'='*100}")
    print("CN_METAL — ATR stop vs Structural stop  (h=opposing, K=3)")
    print("="*100)
    for label,sub in [
        ("ALL h=opp",       oos),
        ("DIF<0 h=opp",     oos[~oos["dif_pos"]]),
        ("DIF>0 h=opp",     oos[oos["dif_pos"]]),
        ("BULL phase",      oos[oos["phase"]=="BULL"]),
        ("TR phase",        oos[oos["phase"].isin(["TR","TR_FORMING"])]),
        ("BEAR phase",      oos[oos["phase"]=="BEAR"]),
    ]:
        ra=sub["r_atr"].dropna(); rs=sub["r_struct"].dropna()
        if ra.empty and rs.empty: continue
        sp=sub["sstop_pct"].dropna(); ap=sub["atr_pct"].dropna()*STOP_MULT
        print(f"\n  [{label}]  n_atr={len(ra)}  n_struct={len(rs)}")
        print(f"    ATR    EV={ra.mean():+.3f}R  {fold(sub,'r_atr')}")
        print(f"    Struct EV={rs.mean():+.3f}R  {fold(sub,'r_struct')}")
        print(f"    Stop dist: ATR={ap.median():.1f}%(med)  Struct={sp.median():.1f}%(med)")

    print(f"\n── Phase distribution (OOS h=opp) ──")
    for ph in ["BULL","TR_FORMING","TR","BEAR","UNCLEAR"]:
        sub=oos[oos["phase"]==ph]
        if sub.empty: continue
        rs=sub["r_struct"].dropna()
        print(f"  {ph:<14}: n={len(sub):3d}  atr={sub['r_atr'].dropna().mean():+.3f}R  struct={rs.mean():+.3f}R")

    df.to_csv("/tmp/pa_cn_structural.csv",index=False)
    print(f"\nSaved /tmp/pa_cn_structural.csv")

if __name__=="__main__":
    main()
