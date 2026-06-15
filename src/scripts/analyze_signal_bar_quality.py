"""analyze_signal_bar_quality.py — does SIGNAL-BAR QUALITY add orthogonal EV on top
of the validated breakout-stop setups? (consolidation/hardening, researcher lane).

The setup-discovery phase is EXHAUSTED: PA alpha is localized to breakout-stop @ structure
boundary (SPEC-001/002/003); all fade/pullback/reversion entries are edgeless (R006/R008/R009).
Next question is orthogonal: WITHIN the breakout-stop population, do high-quality signal bars
(body_frac, close_pos, range_vs_avg) earn higher EV than low-quality ones? If yes, a quality
filter hardens the setups without changing the entry mechanism. This mirrors the researcher
swing-quality finding (tight|wick independent; range_vs_avg 棒长惩罚 the only positive PA-sweep
orthogonal) — we test whether it transfers to the faithful replica breakout corpus.

Read-only: reuses the CANONICAL evaluate() (same simulate_order EV derivation as the validated
tool) and just JOINs features_det back by id. No change to eval_spec001_corpus numbers.

Usage (pooled rb+cu+au breakout-long):
  cd src && TP=/home/drwho1985/workspace/quant/strats/trade-philosopher/runs/_replica
  python3 scripts/analyze_signal_bar_quality.py \
      --corpus $TP/pa_dataset_rb_claude.jsonl $TP/labels_cu.jsonl $TP/labels_au.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from scripts.eval_spec001_corpus import (
    LONG,
    _bootstrap_mean,
    _stats,
    evaluate,
)
from scripts.eval_spec001_ev import _DEFAULT_TP_SRC

# Quality orientation per field: +1 = higher value is higher quality; -1 = lower value
# is higher quality (penalty). body_frac (body size) and the range penalties are
# direction-agnostic; close_pos = (c-low)/range is DIRECTIONAL — a strong bullish bar
# closes near the high (+1 for long), a strong bearish bar near the low (-1 for short).
QUALITY_FIELDS = ("body_frac", "close_pos", "range_vs_avg", "bar_range")


def quality_directions(trade_direction: str) -> dict[str, int]:
    return {
        "body_frac": 1,
        "close_pos": 1 if trade_direction == LONG else -1,
        "range_vs_avg": -1,   # long bars are a penalty (R006-sweep 棒长惩罚)
        "bar_range": -1,
    }


def _features_by_id(corpus_paths: list[Path]) -> dict[str, dict]:
    """id -> features_det (signal-bar geometry recorded at the decision node)."""
    out: dict[str, dict] = {}
    for p in corpus_paths:
        for ln in Path(p).read_text().splitlines():
            if not ln.strip():
                continue
            r = json.loads(ln)
            fd = r.get("features_det") or {}
            if r.get("id"):
                out[r["id"]] = fd
    return out


def stratify(rows: list[dict], feats: dict[str, dict], field: str,
             direction: int = 1) -> dict | None:
    """Split resolved breakout trades at the MEDIAN of `field`, then orient the halves
    by QUALITY: `direction=+1` → higher value is better quality; `direction=-1` → lower
    value is better quality (penalty metric). `ev_delta_better_minus_worse` is therefore
    sign-consistent across metrics: positive ⇒ better-quality bars earn more EV.
    Returns None if too few trades carry the metric to split meaningfully."""
    paired = [(r["gross_r"], feats.get(r["id"], {}).get(field))
              for r in rows if r.get("id") is not None]
    paired = [(g, v) for g, v in paired if v is not None]
    if len(paired) < 8:
        return None
    vals = np.array([v for _, v in paired], float)
    med = float(np.median(vals))
    hi_val = [g for g, v in paired if v >= med]   # higher raw value
    lo_val = [g for g, v in paired if v < med]    # lower raw value
    if not hi_val or not lo_val:
        return None
    better, worse = (hi_val, lo_val) if direction >= 0 else (lo_val, hi_val)
    return {
        "field": field, "median_split": round(med, 4), "n_with_metric": len(paired),
        "direction": "higher_is_better" if direction >= 0 else "lower_is_better(penalty)",
        "better_quality": {**_stats(better), **_bootstrap_mean(better)},
        "worse_quality": {**_stats(worse), **_bootstrap_mean(worse)},
        "ev_delta_better_minus_worse": round(float(np.mean(better) - np.mean(worse)), 4),
    }


def _instrument(contract: str) -> str:
    return "".join(c for c in (contract or "") if not c.isdigit()) or "?"


def analyze(corpus_paths, tp_src, *, cycle, direction) -> dict:
    rep = evaluate(corpus_paths, tp_src, cost_r=0.0, fwd_days=25,
                   max_wait_bars=288, max_hold_bars=288, cycle=cycle, direction=direction)
    resolved = [r for r in rep["orders"] if r.get("triggered") and r.get("resolved")]
    feats = _features_by_id([Path(p) for p in corpus_paths])

    def _has_feat(r):
        fd = feats.get(r["id"], {})
        return any(fd.get(f) is not None for f in QUALITY_FIELDS)

    with_feat = [r for r in resolved if _has_feat(r)]
    missing = [r for r in resolved if not _has_feat(r)]
    miss_by_inst: dict[str, int] = {}
    for r in missing:
        inst = _instrument(r.get("contract", ""))
        miss_by_inst[inst] = miss_by_inst.get(inst, 0) + 1

    qdir = quality_directions(direction)
    strat = {}
    for f in QUALITY_FIELDS:
        s = stratify(resolved, feats, f, qdir[f])
        if s is not None:
            strat[f] = s
    return {
        "population": {
            "direction": direction, "cycle": cycle,
            "n_resolved_breakout": len(resolved),
            "n_with_features": len(with_feat),
            "n_missing_features": len(missing),
            "missing_features_by_instrument": miss_by_inst,
            # full-pool baseline (all resolved) — NOT comparable to strata if coverage<100%
            "baseline_ev_all": _stats([r["gross_r"] for r in resolved]),
            "baseline_ci_all": _bootstrap_mean([r["gross_r"] for r in resolved]),
            # apples-to-apples baseline: only the feature-bearing trades the strata draw from
            "baseline_ev_feature_subset": _stats([r["gross_r"] for r in with_feat]),
            "baseline_ci_feature_subset": _bootstrap_mean([r["gross_r"] for r in with_feat]),
        },
        "quality_strata": strat,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", type=Path, nargs="+", default=None)
    ap.add_argument("--cycle", nargs="+", default=None)
    ap.add_argument("--direction", default=LONG)
    ap.add_argument("--philosopher-src", type=Path, default=_DEFAULT_TP_SRC)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    corpus = args.corpus or [args.philosopher_src.parent / "runs/_replica/pa_dataset_rb_claude.jsonl"]
    rep = analyze(corpus, args.philosopher_src, cycle=args.cycle, direction=args.direction)
    txt = json.dumps(rep, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(txt)

    pop = rep["population"]
    b = pop["baseline_ev_all"]
    print(f"baseline breakout {args.direction} ALL (n={b.get('n')}): EV={b.get('mean_gross_r')} "
          f"win={b.get('win_rate')} CI={pop['baseline_ci_all']['ci95']}")
    if pop["n_missing_features"]:
        fb = pop["baseline_ev_feature_subset"]
        print(f"  ⚠ {pop['n_missing_features']}/{pop['n_resolved_breakout']} resolved trades lack "
              f"features_det ({pop['missing_features_by_instrument']}) → strata are on the "
              f"feature-bearing subset only. Apples-to-apples baseline (feature subset, "
              f"n={fb.get('n')}): EV={fb.get('mean_gross_r')} CI={pop['baseline_ci_feature_subset']['ci95']}")
    for f, s in rep["quality_strata"].items():
        bq, wq = s["better_quality"], s["worse_quality"]
        print(f"  [{f}] ({s['direction']}) split@{s['median_split']} (n={s['n_with_metric']}): "
              f"better EV={bq.get('mean_gross_r')} (n={bq.get('n')},win={bq.get('win_rate')},CI={bq['ci95']}) "
              f"vs worse EV={wq.get('mean_gross_r')} (n={wq.get('n')},win={wq.get('win_rate')},CI={wq['ci95']}) "
              f"| delta(better-worse)={s['ev_delta_better_minus_worse']}")
    if not rep["quality_strata"]:
        print("  (no quality metric present on enough trades to stratify)")


if __name__ == "__main__":
    main()
