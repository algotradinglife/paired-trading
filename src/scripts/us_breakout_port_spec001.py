"""us_breakout_port_spec001.py — CardB (t_b918daa8): port the VALIDATED spec001_proxy
breakout detector to US index ETFs (SPY/QQQ/IWM 5min RTH) and judge whether the
SPEC-001/002/003 breakout-stop edge is cross-market deployable.

Distinct from the philosopher's pass: they used their own coarse `breakout_candidate`
(which over-surfaced mid-range noise) and a structural gate. This runs the ACTUAL
`scripts.backtest_spec001_proxy.detect_signals` — the same deterministic, no-lookahead
breakout detector used on CN (strong-body + close-upper-third + at-lower-boundary +
preceding down-leg + second-entry + payoff gate) — on US bars, then simulates the canonical
breakout-stop exit (`eval_spec001_ev.simulate_order`) and reports EV with bootstrap CI.

Data: US 5min via the sanctioned loader (`data.bar_loader.load_bars_quant_or_json`, the same
one backtest_full_stack uses); bars are period-end-labeled and already RTH (ET 9:35-16:00).
Read-only consumption; no data-pipeline code touched.

Usage:
  cd src && ./.venv/bin/python scripts/us_breakout_port_spec001.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from data import bar_loader
from scripts.backtest_spec001_proxy import detect_signals
from scripts.eval_spec001_ev import _utc, simulate_order

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
SYMBOLS = ("SPY", "QQQ", "IWM")
BOOTSTRAP_N = 5000
BOOTSTRAP_SEED = 12345


def _bars_list(sym: str) -> list[dict]:
    """Load US 5min as a chronological list of bar dicts (open/high/low/close/ts_open).
    ts_open = epoch seconds (the loader's `time` col); _utc() consumes seconds. Already RTH."""
    df = bar_loader.load_bars_quant_or_json(sym, "_5", DATA_DIR)
    if df is None or not len(df):
        return []
    df = df.sort_values("time")
    return [{"open": float(r.open), "high": float(r.high), "low": float(r.low),
             "close": float(r.close), "ts_open": int(r.time)}
            for r in df.itertuples(index=False)]


def _boot_ci(x: np.ndarray) -> list:
    if len(x) < 4:
        return [None, None]
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    m = x[rng.integers(0, len(x), (BOOTSTRAP_N, len(x)))].mean(axis=1)
    return [round(float(np.percentile(m, 2.5)), 3), round(float(np.percentile(m, 97.5)), 3)]


def _stats(rs: list[float]) -> dict:
    if not rs:
        return {"n": 0}
    a = np.array(rs, float)
    return {"n": len(a), "ev": round(float(a.mean()), 4), "win": round(float((a > 0).mean()), 4),
            "median": round(float(np.median(a)), 4), "ci": _boot_ci(a),
            "max": round(float(a.max()), 2), "min": round(float(a.min()), 2)}


def evaluate(*, max_wait_bars: int, max_hold_bars: int) -> dict:
    per_sym = {}
    pooled: list[float] = []
    for sym in SYMBOLS:
        bars = _bars_list(sym)
        if not bars:
            per_sym[sym] = {"n_signals": 0, "note": "no 5min data"}
            continue
        sigs = detect_signals(bars)
        rs = []
        tally = {"resolved": 0, "triggered_unresolved": 0, "no_trigger": 0,
                 "data_exhausted": 0, "sim_none": 0}
        for s in sigs:
            order = {"order_direction": s["order_direction"], "entry": s["entry"],
                     "stop": s["stop"], "target": s["target"]}
            node_end = _utc(bars[s["i"]]["ts_open"])
            sim = simulate_order(order, bars, node_end=node_end,
                                 max_wait_bars=max_wait_bars, max_hold_bars=max_hold_bars,
                                 cost_r=0.0)
            if sim is None:
                tally["sim_none"] += 1
                continue
            kind = sim.get("exit_kind")
            if sim.get("triggered") and sim.get("resolved") and sim.get("gross_r") is not None:
                rs.append(sim["gross_r"])
                tally["resolved"] += 1
            elif sim.get("triggered") and not sim.get("resolved"):
                tally["triggered_unresolved"] += 1          # entry hit, exit data ran out
            elif kind == "entry_data_exhausted":
                tally["data_exhausted"] += 1                # never triggered, data ran out → unknown
            else:
                tally["no_trigger"] += 1                    # breakout level never reached (true no-trade)
        # every detected signal is accounted for in exactly one bucket
        assert sum(tally.values()) == len(sigs), (sym, tally, len(sigs))
        per_sym[sym] = {"n_bars": len(bars), "n_signals": len(sigs),
                        "n_resolved": tally["resolved"], "outcome_tally": tally,
                        "resolved_stats": _stats(rs)}
        pooled.extend(rs)
    return {
        "params": {"max_wait_bars": max_wait_bars, "max_hold_bars": max_hold_bars,
                   "symbols": SYMBOLS, "detector": "spec001_proxy (validated CN breakout)",
                   "note": "US 5min RTH (period-end labeled); canonical breakout-stop exit"},
        "by_symbol": per_sym,
        "pooled_resolved": _stats(pooled),
    }


def _print(rep: dict) -> None:
    print("=== CardB: spec001_proxy breakout ported to US index ETFs (SPY/QQQ/IWM 5min RTH) ===")
    print(f"params: {rep['params']}")
    for sym, s in rep["by_symbol"].items():
        if not s.get("n_signals"):
            print(f"  {sym}: {s.get('note', 'no signals')}")
            continue
        rsv = s["resolved_stats"]
        if rsv.get("n"):
            print(f"  {sym:<4} signals={s['n_signals']:>4} | outcomes={s['outcome_tally']}")
            print(f"       resolved n={rsv['n']} EV={rsv['ev']:+.4f} win={rsv['win']} "
                  f"CI={rsv['ci']} (min {rsv['min']}/max {rsv['max']})")
        else:
            print(f"  {sym:<4} signals={s['n_signals']} resolved=0 outcomes={s['outcome_tally']}")
    p = rep["pooled_resolved"]
    if p.get("n"):
        print(f"\n  POOLED resolved n={p['n']}: EV={p['ev']:+.4f} win={p['win']} CI={p['ci']}")
        verdict = "EV>0 且 CI 排除 0 → 有迹象" if (p["ci"][0] is not None and p["ci"][0] > 0) \
            else "EV<=0 或 CI 跨 0 → 突破 edge 不跨市场到 US 指数 ETF"
        print(f"  VERDICT: {verdict}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max-wait-bars", type=int, default=78)    # ~1 RTH session to trigger
    ap.add_argument("--max-hold-bars", type=int, default=234)   # ~3 RTH sessions to resolve
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    rep = evaluate(max_wait_bars=args.max_wait_bars, max_hold_bars=args.max_hold_bars)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(rep, ensure_ascii=False, indent=2))
    _print(rep)


if __name__ == "__main__":
    main()
