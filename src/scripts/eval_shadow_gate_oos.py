"""eval_shadow_gate_oos.py — OOS / deployment evaluation of the ADVISORY signal-bar
quality gate shipped (shadow) in score_today (commit 057c81f, t_ffffa8fd).

Two questions the hardening doc flagged as the next step before any active sizing
(doc/signal-bar-quality-hardening-2026-06-15, §"局限 & 下一步" (a)/(d)):

  Q1 (DEPLOYMENT FIDELITY) — score_today ships FIXED thresholds
     SIGNAL_BAR_BODY_FRAC_MIN=0.5, SIGNAL_BAR_CLOSE_EXTREME=0.66, but the in-sample
     finding came from per-cohort MEDIAN splits (body_frac med≈0.8, close_pos med≈1.0).
     Does the deployed flag, with its fixed thresholds, reproduce the double-strong EV
     separation — or does it pass (nearly) everything and discriminate nothing?

  Q2 (OUT-OF-SAMPLE) — derive the split RULE on `train` rows only, freeze it, and apply
     to the held-out `test` rows. Does the double-strong conjunction survive OOS?

Read-only. Reuses the CANONICAL evaluate() (same EV derivation as the validated tool),
imports the SHIPPED gate logic directly from score_today (no re-implementation), and
JOINs split/ts_utc/features_det back by id.

Usage:
  cd src && python3 scripts/eval_shadow_gate_oos.py \
      --corpus data/review/pa_dataset_rbcuau.labeled.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from scripts.eval_spec001_corpus import LONG, _bootstrap_mean, _stats, evaluate
from scripts.eval_spec001_ev import _DEFAULT_TP_SRC
# Import the SHIPPED gate verbatim so the eval can never drift from production.
from scripts.score_today import (
    SIGNAL_BAR_BODY_FRAC_MIN,
    SIGNAL_BAR_CLOSE_EXTREME,
    _signal_bar_quality,
)


def _corpus_index(corpus_paths: list[Path]) -> dict[str, dict]:
    """id -> {features_det, split, ts_utc}."""
    out: dict[str, dict] = {}
    for p in corpus_paths:
        for ln in Path(p).read_text().splitlines():
            if not ln.strip():
                continue
            r = json.loads(ln)
            if r.get("id"):
                out[r["id"]] = {
                    "fd": r.get("features_det") or {},
                    "split": r.get("split"),
                    "ts_utc": r.get("ts_utc"),
                }
    return out


SHORT = "做空"


def _gate_dir(direction: str) -> str:
    """Map the evaluate() trade direction (做多/做空) to the score_today gate's
    orientation token. The shipped _signal_bar_quality treats ONLY 'top' as short-like
    (close near low); anything else is long-like (close near high)."""
    return "top" if direction == SHORT else "bottom"


def _ev(rs: list[float]) -> dict:
    return {**_stats(rs), **_bootstrap_mean(rs)}


def _shipped_flag(fd: dict, gate_dir: str) -> bool | None:
    """Apply the EXACT shipped _signal_bar_quality double_strong flag from features_det.
    features_det carries body_frac & close_pos directly; reconstruct an o/h/l/c that yields
    those exact values so we route through the production function (faithful, not a copy)."""
    bf, cp = fd.get("body_frac"), fd.get("close_pos")
    if bf is None or cp is None:
        return None
    # Synthesize a unit-range bar: low=0, high=1, close=cp, open chosen so |c-o|/1 == bf.
    # For long-like bars close>open; clamp open into [0,1]. body_frac/close_pos are what the
    # gate reads, so any o/h/l/c reproducing them gives the identical double_strong verdict.
    low, high, c = 0.0, 1.0, float(cp)
    o = c - float(bf)
    if o < 0.0:                      # body would exceed close-to-low; place body above close
        o = c + float(bf)
    o = min(max(o, 0.0), 1.0)
    q = _signal_bar_quality(o, high, low, c, gate_dir)
    # Guard: our synthetic body_frac must match within rounding, else skip (don't fabricate).
    if q["body_frac"] is None or abs(q["body_frac"] - round(float(bf), 3)) > 0.051:
        return None
    return q["double_strong"]


def _cell_split(rows, feats, direction, body_thr, close_thr):
    """2x2 partition under explicit thresholds (body_frac>=body_thr; close oriented).
    `close_thr` is the RAW close_pos train median, so the short B condition is
    `cp <= close_thr` directly (NOT 1-close_thr — that would invert a low median)."""
    cells = {"A&B": [], "A_only": [], "B_only": [], "neither": []}
    for r in rows:
        fd = feats.get(r["id"], {}).get("fd", {})
        bf, cp = fd.get("body_frac"), fd.get("close_pos")
        if bf is None or cp is None:
            continue
        a = bf >= body_thr
        b = (cp >= close_thr) if direction == LONG else (cp <= close_thr)
        g = r["gross_r"]
        cells["A&B" if a and b else "A_only" if a else "B_only" if b else "neither"].append(g)
    return cells


def evaluate_gate(corpus_paths, tp_src, *, cycle, direction) -> dict:
    rep = evaluate(corpus_paths, tp_src, cost_r=0.0, fwd_days=25,
                   max_wait_bars=288, max_hold_bars=288, cycle=cycle, direction=direction)
    resolved = [r for r in rep["orders"] if r.get("triggered") and r.get("resolved")
                and r.get("id") is not None]
    idx = _corpus_index([Path(p) for p in corpus_paths])
    feat_rows = [r for r in resolved
                 if (idx.get(r["id"], {}).get("fd", {}).get("body_frac") is not None
                     and idx.get(r["id"], {}).get("fd", {}).get("close_pos") is not None)]

    # ---- Q1: deployed (shipped fixed-threshold) gate -------------------------------
    gate_dir = _gate_dir(direction)
    passed, failed, skipped = [], [], 0
    for r in feat_rows:
        flag = _shipped_flag(idx[r["id"]]["fd"], gate_dir)
        if flag is None:
            skipped += 1
            continue
        (passed if flag else failed).append(r["gross_r"])
    shipped = {
        "thresholds": {"body_frac_min": SIGNAL_BAR_BODY_FRAC_MIN,
                       "close_extreme": SIGNAL_BAR_CLOSE_EXTREME},
        "n_eval": len(passed) + len(failed), "n_skipped_recon": skipped,
        "n_double_strong": len(passed), "n_not": len(failed),
        "pass_rate": round(len(passed) / max(1, len(passed) + len(failed)), 3),
        "double_strong_ev": _ev(passed) if passed else None,
        "not_ev": _ev(failed) if failed else None,
        "ev_delta": (round(float(np.mean(passed) - np.mean(failed)), 4)
                     if passed and failed else None),
    }

    # ---- Q2: OOS train→test split (derive median rule on train, freeze, apply to test) --
    def _by_split(s):
        return [r for r in feat_rows if idx[r["id"]]["split"] == s]
    train, val, test = _by_split("train"), _by_split("val"), _by_split("test")
    oos = None
    if len(train) >= 8 and len(test) >= 8:
        tr_bf = [idx[r["id"]]["fd"]["body_frac"] for r in train]
        tr_cp = [idx[r["id"]]["fd"]["close_pos"] for r in train]
        body_thr = float(np.median(tr_bf))
        close_thr = float(np.median(tr_cp))   # oriented in _cell_split

        def _summ(rows):
            cells = _cell_split(rows, idx, direction, body_thr, close_thr)
            return {
                "n": len(rows),
                "cells": {k: _stats(v) for k, v in cells.items()},
                "double_strong_ev": _ev(cells["A&B"]) if cells["A&B"] else None,
                "rest_ev": _ev(cells["A_only"] + cells["B_only"] + cells["neither"])
                if (cells["A_only"] or cells["B_only"] or cells["neither"]) else None,
            }
        oos = {
            "rule_from_train": {"body_frac_thr": round(body_thr, 4),
                                "close_pos_thr": round(close_thr, 4)},
            "train": _summ(train), "val": _summ(val), "test": _summ(test),
            "test_plus_val": _summ(val + test),
        }

    return {
        "population": {
            "direction": direction, "cycle": cycle,
            "n_resolved": len(resolved), "n_with_features": len(feat_rows),
            "baseline_ev": _ev([r["gross_r"] for r in feat_rows]),
            "split_counts": {s: len(_by_split(s)) for s in ("train", "val", "test", None)},
        },
        "q1_shipped_gate": shipped,
        "q2_oos_split": oos,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", type=Path, nargs="+", required=True)
    ap.add_argument("--cycle", nargs="+", default=None)
    ap.add_argument("--direction", default=LONG)
    ap.add_argument("--philosopher-src", type=Path, default=_DEFAULT_TP_SRC)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    rep = evaluate_gate(args.corpus, args.philosopher_src,
                        cycle=args.cycle, direction=args.direction)
    txt = json.dumps(rep, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(txt)

    pop = rep["population"]
    b = pop["baseline_ev"]
    print(f"=== Shadow signal-bar gate — OOS / deployment eval ({args.direction}) ===")
    print(f"population: n_resolved={pop['n_resolved']} n_with_features={pop['n_with_features']} "
          f"baseline EV={b.get('mean_gross_r')} CI={b['ci95']}")
    print(f"split counts (feature-bearing): {pop['split_counts']}")

    s = rep["q1_shipped_gate"]
    print(f"\n[Q1] DEPLOYED gate (body_frac>={s['thresholds']['body_frac_min']}, "
          f"close_extreme={s['thresholds']['close_extreme']}):")
    print(f"  double_strong pass_rate={s['pass_rate']}  "
          f"(n_pass={s['n_double_strong']}/{s['n_eval']}, skipped_recon={s['n_skipped_recon']})")
    if s["double_strong_ev"] and s["not_ev"]:
        print(f"  double_strong EV={s['double_strong_ev']['mean_gross_r']} "
              f"CI={s['double_strong_ev']['ci95']}  vs  not EV={s['not_ev']['mean_gross_r']} "
              f"CI={s['not_ev']['ci95']}  | delta={s['ev_delta']}")
    else:
        print(f"  ⚠ DEGENERATE: gate does not partition the population "
              f"(double_strong={s['n_double_strong']}, not={s['n_not']}) → no EV contrast possible.")

    o = rep["q2_oos_split"]
    print("\n[Q2] OOS train→test (median rule frozen on train, applied to held-out):")
    if o is None:
        print("  (insufficient train/test trades to split)")
    else:
        r = o["rule_from_train"]
        _cop = "<=" if args.direction == SHORT else ">="
        print(f"  rule from train: body_frac>={r['body_frac_thr']}, close_pos{_cop}{r['close_pos_thr']}")
        for name in ("train", "val", "test", "test_plus_val"):
            seg = o[name]
            ab = seg["cells"]["A&B"]
            ds = seg["double_strong_ev"]
            rest = seg["rest_ev"]
            line = (f"  {name:<13} n={seg['n']:>3}  double_strong n={ab.get('n')} "
                    f"EV={ds['mean_gross_r'] if ds else None}")
            if ds:
                line += f" CI={ds['ci95']}"
            if rest:
                line += f"  | rest EV={rest['mean_gross_r']} (n={rest.get('n')})"
            print(line)
        print("    cells per segment (A=body-strong, B=close-strong):")
        for name in ("train", "test"):
            cells = o[name]["cells"]
            print("      %-5s " % name + ", ".join(
                f"{k} n={v.get('n')} EV={v.get('mean_gross_r')}" for k, v in cells.items()))


if __name__ == "__main__":
    main()
