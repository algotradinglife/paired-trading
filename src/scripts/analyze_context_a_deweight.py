"""analyze_context_a_deweight.py — P3a: port-validate the over-extension /
second-entry de-weight on the LIVE context_a lane (kanban t_50cb7876).

The de-weight (w_a(range_vs_avg) × w_b(ordinal), bottom side) was validated on the
RESEARCH population (detect_all_divergences bottom×opposing, gated by apply_policy).
Production ships bottom×opposing via ContextADetector.policy_weight (DIF>0 uptrend
pullback, h=opposing) — a DIFFERENT population. Before wiring the factor into the
live lane we must check the edge TRANSFERS here.

This reuses the context_a backtest convention verbatim (scan_context_a / simulate_trade
from backtest_context_a_ev: stop=1.5×ATR, 1R:1R:1.5R, max_hold=40, min_gap=10) and the
production de-weight modules (engine.divergence.overext_features /.overext_deweight) so
the numbers reflect exactly what P3b would ship. Restricted to h=opposing (the live gate).

**Mechanical statistics only — no PASS/FAIL verdict.** Reports the w_a/w_b EV shapes on
this population, three weighting schemes (equal / hard-AND / production continuous
factor), the continuous-vs-equal bootstrap gap, and the lane's K=3 periods (IS/F1/F2/F3).

Usage:
  python3 scripts/analyze_context_a_deweight.py --out data/review/context_a_deweight.json
  (data/raw JSON bars; US + CN_METAL context_a symbol universe)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from data import bar_loader
from engine.divergence import overext_features as of
from engine.divergence.overext_deweight import W_MIN, deweight_factor, w_a, w_b
from scripts.backtest_context_a_ev import (
    CUTOFF_IS,
    CUTOFF_OOS1,
    CUTOFF_OOS2,
    POOLS,
    compute_atr,
    scan_context_a,
)
from scripts.backtest_rr_pool import _load_sym

BOOTSTRAP_N = 10000
BOOTSTRAP_SEED = 42
STOP_MULT = 1.5  # context_a lane default


def _factor(row: dict) -> float:
    """Production de-weight factor for a context_a (bottom, opposing) signal."""
    return deweight_factor("bottom", "opposing", row["range_vs_avg"], row["ordinal"])


def collect_rows(quant_root: Path) -> list[dict]:
    """context_a × h=opposing events with realized_r + range_vs_avg + ordinal + date."""
    rows: list[dict] = []
    for pool, (symbols, _icls) in POOLS.items():
        for sym in symbols:
            bars = _load_sym(sym, "D", quant_root)
            if bars is None or bars.empty:
                print(f"  {pool}/{sym}: no daily bars, skip", file=sys.stderr)
                continue
            h_bars = _load_sym(sym, "60min", quant_root)
            atr = compute_atr(bars)
            recs = scan_context_a(bars, h_bars, STOP_MULT, atr)
            ctx = of.prepare_context(bars)  # de-weight's own ATR + swing lows
            kept = 0
            for rec in recs:
                if rec["h_rel"] != "opposing":
                    continue
                idx = rec["bar_idx"]
                rva = of.range_vs_avg(bars, idx)
                if rva is None or not np.isfinite(rva):
                    continue  # mirror research: drop unassessable bars
                ordn = of.test_ordinal(bars, idx, ctx)
                if ordn is None:
                    continue
                rows.append({
                    "pool": pool, "symbol": sym, "bar_idx": idx,
                    "date": rec["timestamp"].date().isoformat(),
                    "period": rec["period"], "realized_r": float(rec["r"]),
                    "range_vs_avg": float(rva), "ordinal": int(ordn),
                    "win": int(rec["r"] > 0),
                })
                kept += 1
            print(f"  {pool}/{sym}: {kept} opposing events", file=sys.stderr)
    return rows


def _ev(rows: list[dict]) -> float | None:
    return round(float(np.mean([r["realized_r"] for r in rows])), 6) if rows else None


def _weighted_ev(rows: list[dict], wfn) -> dict:
    if not rows:
        return {"n": 0, "weighted_ev": None, "eff_n": 0.0}
    w = np.array([wfn(r) for r in rows], dtype=float)
    r = np.array([x["realized_r"] for x in rows], dtype=float)
    sw = w.sum()
    eff_n = float(sw * sw / np.sum(w * w)) if np.sum(w * w) > 0 else 0.0
    return {"n": len(rows),
            "weighted_ev": round(float(np.sum(w * r) / sw), 6) if sw > 0 else None,
            "eff_n": round(eff_n, 1)}


def _bootstrap_weighted_gap(rows: list[dict], wfn) -> dict:
    if len(rows) < 4:
        return {"gap": None, "ci95": [None, None], "p_gt0": None}
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    w = np.array([wfn(r) for r in rows])
    r = np.array([x["realized_r"] for x in rows])
    diffs = []
    for _ in range(BOOTSTRAP_N):
        idx = rng.integers(0, len(rows), len(rows))
        ww, rr = w[idx], r[idx]
        if ww.sum() <= 0:
            continue
        diffs.append(float(np.sum(ww * rr) / ww.sum() - rr.mean()))
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return {"gap": round(float(np.mean(diffs)), 6),
            "ci95": [round(float(lo), 6), round(float(hi), 6)],
            "p_gt0": round(float(np.mean(np.array(diffs) > 0)), 4)}


def _wa_quintiles(rows: list[dict]) -> list[dict]:
    rvas = sorted(r["range_vs_avg"] for r in rows)
    if not rvas:
        return []
    qs = np.quantile(rvas, [0, 0.2, 0.4, 0.6, 0.8, 1.0])
    out = []
    for i in range(len(qs) - 1):
        lo, hi = qs[i], qs[i + 1]
        b = ([r for r in rows if lo <= r["range_vs_avg"] <= hi] if i == len(qs) - 2
             else [r for r in rows if lo <= r["range_vs_avg"] < hi])
        out.append({"range": [round(float(lo), 3), round(float(hi), 3)],
                    "n": len(b), "ev": _ev(b), "w_a_mid": round(w_a((lo + hi) / 2), 3)})
    return out


def _wb_by_ordinal(rows: list[dict]) -> dict:
    out = {}
    for o in (1, 2, 3):
        b = [r for r in rows if min(r["ordinal"], 3) == o]
        out[str(o)] = {"n": len(b), "ev": _ev(b), "w_b": round(w_b(o), 3)}
    return out


def _period_breakdown(rows: list[dict]) -> dict:
    out = {}
    for p, label in [("IS", "IS"), ("OOS1", "F1"), ("OOS2", "F2"), ("OOS3", "F3")]:
        seg = [r for r in rows if r["period"] == p]
        out[label] = {
            "n": len(seg), "equal_ev": _ev(seg),
            "continuous": _weighted_ev(seg, _factor),
        }
    return out


def build_report(rows: list[dict]) -> dict:
    hard_and = [r for r in rows if r["range_vs_avg"] <= 1.0 and r["ordinal"] == 1]
    schemes = {
        "full_equal": {"n": len(rows), "ev": _ev(rows), "eff_n": len(rows)},
        "hard_AND_gate": {"n": len(hard_and), "ev": _ev(hard_and), "eff_n": len(hard_and)},
        "continuous_weight": _weighted_ev(rows, _factor),
    }

    def pool_block(subset):
        return {
            "n": len(subset),
            "w_a_shape_quintiles": _wa_quintiles(subset),
            "w_b_shape_by_ordinal": _wb_by_ordinal(subset),
            "scheme_comparison": {
                "full_equal": {"n": len(subset), "ev": _ev(subset)},
                "continuous_weight": _weighted_ev(subset, _factor),
            },
            "continuous_vs_equal_bootstrap": _bootstrap_weighted_gap(subset, _factor),
        }

    return {
        "params": {
            "population": "context_a (DIF>0 pullback) × higher_tf_relation=opposing",
            "lane_convention": "scan_context_a/simulate_trade (stop=1.5×ATR, "
                               "1R:1R:1.5R, max_hold=40, min_gap=10)",
            "de_weight": "engine.divergence.overext_deweight.deweight_factor "
                         f"(w_a×w_b, bottom×opposing; w_min={W_MIN})",
            "cutoffs": {"IS": str(CUTOFF_IS.date()), "OOS1": str(CUTOFF_OOS1.date()),
                        "OOS2": str(CUTOFF_OOS2.date())},
            "note": "mechanical statistics; no PASS/FAIL; P3b live wiring decided "
                    "from whether the edge transfers (weighted vs equal gap CI/period sign)",
        },
        "n": len(rows),
        "combined": {
            "w_a_shape_quintiles": _wa_quintiles(rows),
            "w_b_shape_by_ordinal": _wb_by_ordinal(rows),
            "scheme_comparison": schemes,
            "continuous_vs_equal_bootstrap": _bootstrap_weighted_gap(rows, _factor),
            "period_breakdown": _period_breakdown(rows),
        },
        "by_pool": {pool: pool_block([r for r in rows if r["pool"] == pool])
                    for pool in POOLS},
        "events": rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quant-root", type=Path, default=bar_loader.DEFAULT_QUANT_ROOT)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    rows = collect_rows(args.quant_root)
    report = build_report(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    s = report["combined"]["scheme_comparison"]
    b = report["combined"]["continuous_vs_equal_bootstrap"]
    print(f"wrote {args.out}  (n={report['n']} "
          f"equal_ev={s['full_equal']['ev']} "
          f"cont_wev={s['continuous_weight']['weighted_ev']}"
          f"(eff_n={s['continuous_weight']['eff_n']}) "
          f"gap={b['gap']} ci={b['ci95']} P={b['p_gt0']})")


if __name__ == "__main__":
    main()
