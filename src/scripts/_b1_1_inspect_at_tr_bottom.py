"""Inspect at_tr_bottom gate pass-rate on pa_us_dif_pos over last 365 days.

Mirrors the filter cascade in score_today.py us_equity daily branch:
  1. DIF > 0
  2. h=opposing
  3. phase NOT in {BEAR, UNCLEAR}
  4. structural_stop present & < close

Then, for each surviving signal that lands in TR/TR_FORMING, tabulates the
distribution of pos_in_tr and reports how the gate counts shift under
candidate thresholds (0.25 = current, 0.40, 0.50, no gate).

Run from src/ via .venv/bin/python.
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from data import bar_loader
from engine.divergence.pa_detector import PABottomDetector, PASignal
from engine.divergence.pa_structure import PAStructureDetector
from engine.features.macd import macd


POOL_US = ["SPY", "QQQ", "IWM", "DIA", "GLD", "GDX", "XLF", "XLK",
           "TLT", "NVDA", "XLB", "XLE", "XLRE", "XLU"]


def _load_daily(sym: str, root: Path) -> pd.DataFrame | None:
    resolved = bar_loader.infer_symbol_and_mic(sym)
    if resolved is None:
        return None
    quant_sym, mic = resolved
    try:
        return bar_loader.load_bars_quant(quant_sym, mic, "D", root)
    except Exception as e:
        print(f"  daily load fail {sym}: {e}", file=sys.stderr)
        return None


def _load_60(sym: str, root: Path) -> pd.DataFrame | None:
    resolved = bar_loader.infer_symbol_and_mic(sym)
    if resolved is None:
        return None
    quant_sym, mic = resolved
    try:
        return bar_loader.load_bars_quant(quant_sym, mic, "60min", root)
    except Exception as e:
        print(f"  60min load fail {sym}: {e}", file=sys.stderr)
        return None


def main() -> int:
    quant_root = Path(os.environ.get("QUANT_ROOT", str(bar_loader.DEFAULT_QUANT_ROOT)))
    window_days = int(os.environ.get("WINDOW_DAYS", "365"))
    cutoff = date.today() - timedelta(days=window_days)
    print(f"window_days={window_days} cutoff={cutoff} quant_root={quant_root}")

    pa_struct_det = PAStructureDetector()
    pa_det = PABottomDetector(
        min_h_legs=2, min_quality=0.3, ema_threshold=0.0, min_gap=10,
    )

    rows: list[dict] = []
    for sym in POOL_US:
        if sym.lower() in PABottomDetector.US_LONG_BOND_SUPPRESS:
            continue
        bars = _load_daily(sym, quant_root)
        if bars is None or len(bars) < 100:
            print(f"  skip {sym}: no daily bars")
            continue
        h_bars = _load_60(sym, quant_root)
        if h_bars is None or len(h_bars) < 100:
            print(f"  skip {sym}: no 60min bars")
            continue
        macd_df = macd(bars["close"], hist_scale=1.0)
        sigs: list[PASignal] = pa_det.scan(bars, h_bars)
        for sig in sigs:
            if sig.timestamp.date() < cutoff:
                continue
            row = {
                "symbol": sym, "date": sig.timestamp.date(),
                "dif": float(macd_df["dif"].iloc[sig.bar_idx]),
                "h": sig.higher_tf_relation,
                "phase": None, "pos_in_tr": None,
                "stop": None, "close": None,
                "stop_ok": False, "dif_ok": False, "h_ok": False,
                "phase_ok": False,
            }
            # Cascade filters
            row["dif_ok"] = row["dif"] > 0
            row["h_ok"]   = sig.higher_tf_relation == "opposing"
            struct = pa_struct_det.detect(bars, up_to_idx=sig.bar_idx)
            row["phase"]    = struct.phase
            row["pos_in_tr"] = struct.pos_in_tr
            row["phase_ok"] = struct.phase not in ("BEAR", "UNCLEAR")
            close = float(bars["close"].iloc[sig.bar_idx])
            row["close"] = close
            row["stop"]  = struct.structural_stop
            row["stop_ok"] = (
                struct.structural_stop is not None
                and struct.structural_stop < close
            )
            rows.append(row)

    df = pd.DataFrame(rows)
    print(f"\nTotal raw PA signals (pre-filter): {len(df)}")
    if df.empty:
        return 0

    pre_tr_gate = df[df["dif_ok"] & df["h_ok"] & df["phase_ok"] & df["stop_ok"]].copy()
    print(f"After DIF>0 + h=opp + phase_ok + stop_ok: {len(pre_tr_gate)}")
    print("  by phase:")
    print(pre_tr_gate["phase"].value_counts().to_string())

    tr_only = pre_tr_gate[pre_tr_gate["phase"].isin(["TR", "TR_FORMING"])]
    bull_only = pre_tr_gate[pre_tr_gate["phase"] == "BULL"]
    print(f"\nTR/TR_FORMING candidates: {len(tr_only)}")
    print(f"BULL candidates:          {len(bull_only)}")

    if not tr_only.empty:
        s = tr_only["pos_in_tr"].dropna()
        print(f"\npos_in_tr distribution among TR/TR_FORMING (n={len(s)}):")
        print(f"  min={s.min():.3f} p25={s.quantile(0.25):.3f} "
              f"median={s.median():.3f} p75={s.quantile(0.75):.3f} "
              f"max={s.max():.3f} mean={s.mean():.3f}")
        # Buckets
        for thr in [0.25, 0.30, 0.35, 0.40, 0.50]:
            n_pass = int((s < thr).sum())
            print(f"  pos_in_tr < {thr:.2f}: {n_pass}/{len(s)} "
                  f"({n_pass / len(s) * 100:.1f}%)")

    # Final emission counts under different policies
    print("\n=== Emission counts under candidate gate policies ===")
    for label, gate_thr in [
        ("a) current gate (<0.25)", 0.25),
        ("b) widen to <0.40",       0.40),
        ("c) widen to <0.50",       0.50),
        ("d) no gate (drop)",       None),
    ]:
        if gate_thr is None:
            emitted = len(pre_tr_gate)
            tr_emit = len(tr_only)
        else:
            tr_emit = int((tr_only["pos_in_tr"] < gate_thr).sum())
            emitted = len(bull_only) + tr_emit
        print(f"  {label:<28s}: total={emitted:3d}  "
              f"(BULL={len(bull_only)}, TR={tr_emit})")

    # Per-symbol TR breakdown
    if not tr_only.empty:
        print("\nTR/TR_FORMING by symbol (showing pos_in_tr):")
        for sym in sorted(tr_only["symbol"].unique()):
            sub = tr_only[tr_only["symbol"] == sym]
            pos_vals = sub["pos_in_tr"].dropna().tolist()
            print(f"  {sym}: n={len(sub)}  pos_in_tr={[f'{x:.2f}' for x in pos_vals]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
