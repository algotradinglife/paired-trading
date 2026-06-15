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
    BOOTSTRAP_N,
    BOOTSTRAP_SEED,
    LONG,
    _bootstrap_mean,
    _stats,
    evaluate,
)
from scripts.eval_spec001_ev import _DEFAULT_TP_SRC


def _bootstrap_diff(a: list[float], b: list[float]) -> list:
    """Bootstrap 95% CI for mean(a)-mean(b) (independent resampling, seed-pinned).
    Used to test whether the intersection's marginal gain over a single filter is
    distinguishable from 0. CI crossing 0 ⇒ not a demonstrated marginal lift."""
    if len(a) < 4 or len(b) < 4:
        return [None, None]
    A, B = np.array(a, float), np.array(b, float)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    da = A[rng.integers(0, len(A), (BOOTSTRAP_N, len(A)))].mean(axis=1)
    db = B[rng.integers(0, len(B), (BOOTSTRAP_N, len(B)))].mean(axis=1)
    d = da - db
    return [round(float(np.percentile(d, 2.5)), 4), round(float(np.percentile(d, 97.5)), 4)]

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


COMBINED_FIELDS = ("body_frac", "close_pos")   # the two strongest single-metric filters


def combined_filter(rows: list[dict], feats: dict[str, dict],
                    fields: tuple[str, ...], qdir: dict[str, int]) -> dict | None:
    """Require a trade to be on the BETTER-quality side of EVERY field in `fields`
    (oriented by qdir). Reports retention + intersection EV, AND (for exactly two
    fields) the 2x2 partition and the MARGINAL contrast of the intersection over each
    single filter with a bootstrap-diff CI. The marginal CI is the honest test of
    'do the two signals add?' — a CI crossing 0 means additivity is NOT demonstrated,
    and single-vs-neither cell EVs show whether a monotone tiering is even supported.
    Median is taken over trades carrying ALL fields. None if too few usable."""
    usable = [r for r in rows
              if all(feats.get(r["id"], {}).get(f) is not None for f in fields)]
    if len(usable) < 8:
        return None
    meds = {f: float(np.median([feats[r["id"]][f] for r in usable])) for f in fields}

    def _flag(r, f):
        v = feats[r["id"]][f]
        return v >= meds[f] if qdir[f] >= 0 else v < meds[f]

    def _passes(r):
        return all(_flag(r, f) for f in fields)

    good = [r["gross_r"] for r in usable if _passes(r)]
    rest = [r["gross_r"] for r in usable if not _passes(r)]
    if not good or not rest:
        return None
    out = {
        "fields": list(fields), "median_split": {f: round(meds[f], 4) for f in fields},
        "n_usable": len(usable), "n_pass": len(good),
        "retention": round(len(good) / len(usable), 3),
        "pass_ev": {**_stats(good), **_bootstrap_mean(good)},
        "fail_ev": {**_stats(rest), **_bootstrap_mean(rest)},
        "ev_delta_pass_minus_fail": round(float(np.mean(good) - np.mean(rest)), 4),
    }
    if len(fields) == 2:
        fa, fb = fields
        cells = {"A&B": [], "A_only": [], "B_only": [], "neither": []}
        a_pass, b_pass = [], []
        for r in usable:
            g, a, b = r["gross_r"], _flag(r, fa), _flag(r, fb)
            if a:
                a_pass.append(g)
            if b:
                b_pass.append(g)
            cells["A&B" if a and b else "A_only" if a else "B_only" if b else "neither"].append(g)
        out["two_by_two"] = {k: _stats(v) for k, v in cells.items()}  # A=fa-strong, B=fb-strong
        ab, a_only, b_only = cells["A&B"], cells["A_only"], cells["B_only"]
        # DISJOINT marginal contrasts (codex: AB ⊂ A_pass → nested resample invalid).
        # "does adding fb help GIVEN fa-strong?" = A&B vs A_only (both fa-strong, disjoint).
        out["marginals"] = {
            # value of adding fb GIVEN fa-strong = A&B (fa&fb) minus A_only (fa, not fb)
            f"marginal_{fb}_given_{fa}": {
                "comparator_cell": "A_only", "delta": round(float(np.mean(ab) - np.mean(a_only)), 4) if a_only else None,
                "ci95_diff": _bootstrap_diff(ab, a_only)},
            # value of adding fa GIVEN fb-strong = A&B minus B_only (fb, not fa)
            f"marginal_{fa}_given_{fb}": {
                "comparator_cell": "B_only", "delta": round(float(np.mean(ab) - np.mean(b_only)), 4) if b_only else None,
                "ci95_diff": _bootstrap_diff(ab, b_only)},
            "note": ("disjoint within-condition contrasts (A&B vs the single-only cell); additivity "
                     "demonstrated only if a marginal CI excludes 0; single-strong cells below 'neither' "
                     "refute a monotone tier"),
        }
    return out


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
    combined = combined_filter(resolved, feats, COMBINED_FIELDS, qdir)
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
        "combined_filter": combined,
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
    cf = rep.get("combined_filter")
    if cf:
        p, fl = cf["pass_ev"], cf["fail_ev"]
        print(f"  COMBINED {cf['fields']}: pass EV={p.get('mean_gross_r')} "
              f"(n={cf['n_pass']}/{cf['n_usable']}, retention={cf['retention']}, "
              f"win={p.get('win_rate')}, CI={p['ci95']}) vs fail EV={fl.get('mean_gross_r')} "
              f"(n={fl.get('n')}, CI={fl['ci95']}) | delta(pass-fail)={cf['ev_delta_pass_minus_fail']}")
        if "two_by_two" in cf:
            cells = cf["two_by_two"]
            print("    2x2 cells (A=%s-strong, B=%s-strong): " % tuple(cf["fields"]) +
                  ", ".join(f"{k} n={v.get('n')} EV={v.get('mean_gross_r')}" for k, v in cells.items()))
            for k, m in cf["marginals"].items():
                if isinstance(m, dict):
                    print(f"    marginal {k}: delta={m['delta']} ci95_diff={m['ci95_diff']}"
                          f"{'  ⚠CI crosses 0 → additivity NOT shown' if (m['ci95_diff'][0] is None or m['ci95_diff'][0] <= 0 <= m['ci95_diff'][1]) else ''}")


if __name__ == "__main__":
    main()
