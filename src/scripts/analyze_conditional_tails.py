"""analyze_conditional_tails.py — Q2-Phase1 of the option-pairing-edge triage
(trade-philosopher doc/pa-replication/option-pairing-edge-triage-2026-06-16.md, card t_49029cd2).

Thesis under test: an option leg on top of a validated DIRECTION signal only earns its
theta+spread cost if it captures CONVEXITY — the underlying's conditional RIGHT TAIL
(big favorable moves after the signal) that a linear underlying position cannot. The
hypothesis is that precious metals (au here; ag pending data) have structurally fatter
conditional right tails than base metals (cu/rb), explaining why ag/au option pairing was
EV+ and cu/rb EV- (DD-line). This script turns "precious-metal upward skew" into a
MEASURED, per-instrument right-tail / skew statistic — no option data needed (Phase 1 free).

It also reports the LEFT tail (MAE) and terminal skew, which answers Q3 a-priori: if the
forward distribution is right-tail-dominant everywhere, a put (left-tail) pairing is
structurally disadvantaged and should be de-prioritized.

Method: reuses the CANONICAL bar loader (_load_cn_window) and the same breakout-spec
selection as the validated eval (eval_spec001_corpus). For each signal it measures, from
the SIGNAL-BAR close S0 (the option-purchase spot) over a fixed forward horizon H, the
UNCAPPED path in ATR units — MFE (max favorable), MAE (max adverse), and terminal return.
Stop/target-capped gross_r (the labels) cannot show convexity; this can.

Read-only consumption of the already-delivered replica bar window (same harness as the
validated SPEC-001 eval). No data-pipeline code touched.

Usage:
  cd src && ./.venv/bin/python scripts/analyze_conditional_tails.py \
      --corpus data/review/pa_dataset_rbcuau.labeled.jsonl
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from scripts.eval_spec001_corpus import (
    LONG,
    SPEC_ORDER_TYPE,
    _decision_dir,
)
from scripts.eval_spec001_ev import _DEFAULT_TP_SRC, _load_cn_window, _utc

BOOTSTRAP_N = 5000
BOOTSTRAP_SEED = 12345
RIGHT_K = (1, 2, 3, 4)     # MFE >= k*ATR thresholds (right-tail / convexity mass)
LEFT_K = (1, 2, 3)         # MAE >= k*ATR thresholds (left-tail / put relevance)
STRIKE_K = (0, 1, 2, 3)    # OTM strike offsets (ATR) for the call/put payoff proxy


def _interval_seconds(interval: str) -> int:
    """Parse a bar interval label ('5min','15min','1h','60min','1d') to seconds.
    Used only to size the load window's bar count; falls back to 5min on anything odd."""
    s = (interval or "").strip().lower()
    try:
        if s.endswith("min"):
            return int(s[:-3]) * 60
        if s.endswith("h"):
            return int(s[:-1]) * 3600
        if s.endswith("d"):
            return int(s[:-1]) * 86400
    except ValueError:
        pass
    return 300


def _instrument(r: dict) -> str:
    return r.get("instrument") or "".join(
        c for c in (r.get("contract") or "") if not c.isdigit()) or "?"


def _skew(x: np.ndarray) -> float | None:
    """Fisher-Pearson sample skewness (g1). None if <3 points or zero variance."""
    if len(x) < 3:
        return None
    m = x.mean()
    s2 = ((x - m) ** 2).mean()
    if s2 <= 0:
        return None
    return float(((x - m) ** 3).mean() / s2 ** 1.5)


def _boot_mean_ci(x: np.ndarray) -> list:
    if len(x) < 4:
        return [None, None]
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    means = x[rng.integers(0, len(x), (BOOTSTRAP_N, len(x)))].mean(axis=1)
    return [round(float(np.percentile(means, 2.5)), 3),
            round(float(np.percentile(means, 97.5)), 3)]


def _forward_path(bars: list[dict], node_end: dt.datetime, atr: float,
                  horizon: int) -> dict | str:
    """From the signal-bar close S0 (last bar at/<= node_end), measure the uncapped
    forward path over the next `horizon` bars in ATR units (long orientation):
      mfe = (max high - S0)/atr, mae = (S0 - min low)/atr, term = (close_H - S0)/atr.
    Returns the path dict, or a skip-reason string ('no_atr'|'no_s0'|'short_horizon')
    so the caller can account for every dropped row (no silent omission)."""
    if atr is None or atr <= 0:
        return "no_atr"
    s0 = None
    for b in bars:                       # bars are chronological
        if _utc(b["ts_open"]) <= node_end:
            s0 = float(b["close"])
        else:
            break
    if s0 is None:                       # signal bar precedes the loaded window → biased drop
        return "no_s0"
    fwd = [b for b in bars if _utc(b["ts_open"]) > node_end][:horizon]
    if len(fwd) < horizon:               # need a full horizon to avoid right-censoring bias
        return "short_horizon"
    highs = max(float(b["high"]) for b in fwd)
    lows = min(float(b["low"]) for b in fwd)
    term = float(fwd[-1]["close"])
    return {"mfe": (highs - s0) / atr, "mae": (s0 - lows) / atr, "term": (term - s0) / atr}


def _summ(paths: list[dict]) -> dict:
    if not paths:
        return {"n": 0}
    mfe = np.array([p["mfe"] for p in paths], float)
    mae = np.array([p["mae"] for p in paths], float)
    term = np.array([p["term"] for p in paths], float)
    out = {
        "n": len(paths),
        "mfe_mean": round(float(mfe.mean()), 3), "mfe_median": round(float(np.median(mfe)), 3),
        "mfe_ci": _boot_mean_ci(mfe),
        "mae_mean": round(float(mae.mean()), 3),
        "term_mean": round(float(term.mean()), 3), "term_skew": (
            round(_skew(term), 3) if _skew(term) is not None else None),
        "right_tail": {f"mfe>={k}": round(float((mfe >= k).mean()), 3) for k in RIGHT_K},
        "left_tail": {f"mae>={k}": round(float((mae >= k).mean()), 3) for k in LEFT_K},
    }
    # convexity asymmetry: how much more often a big favorable move than a big adverse one
    p_mfe2, p_mae2 = float((mfe >= 2).mean()), float((mae >= 2).mean())
    out["asym_p_mfe2_over_mae2"] = round(p_mfe2 / p_mae2, 3) if p_mae2 > 0 else None
    # ---- decision-relevant convexity: expected k-ATR-OTM option intrinsic at horizon ----
    # call pays max(term-k,0); put pays max(-term-k,0). In ATR units, per signal. This is
    # what an option leg actually captures (terminal), unlike vol-swamped excursion masses.
    out["call_payoff"] = {f"k={k}": round(float(np.maximum(term - k, 0).mean()), 3)
                          for k in STRIKE_K}
    out["put_payoff"] = {f"k={k}": round(float(np.maximum(-term - k, 0).mean()), 3)
                         for k in STRIKE_K}
    # right/left convexity ratio at k=1 (the canonical OTM offset): >1 favors calls
    c1, p1 = float(np.maximum(term - 1, 0).mean()), float(np.maximum(-term - 1, 0).mean())
    out["call_over_put_k1"] = round(c1 / p1, 3) if p1 > 0 else None
    return out


def analyze(corpus_path: Path, tp_src: Path, *, fwd_days: int, horizons: list[int]) -> dict:
    load_cn_window = _load_cn_window(tp_src)
    rows = [json.loads(ln) for ln in Path(corpus_path).read_text().splitlines() if ln.strip()]

    # population tags: every candidate carries a breakout entry/atr (structural tail);
    # spec = the replica-selected breakout-long subset (the validated SPEC-001 signal).
    def _is_spec(r):
        d = r.get("decision") or {}
        return d.get("order_type") == SPEC_ORDER_TYPE and _decision_dir(d) == LONG

    # one bar load per contract, sized to span the contract's FULL candidate range
    # (au monthly contracts trade ~380 days ≈ 80k 5min bars — a fixed 8000 window would
    # silently drop early signals and bias toward late-contract samples, codex P2).
    node_span: dict[str, list] = {}     # contract -> [min_node, max_node]
    for r in rows:
        c = r.get("contract")
        if not c:
            continue
        ne = dt.datetime.fromisoformat(r["ts_utc"])
        s = node_span.setdefault(c, [ne, ne])
        if ne < s[0]:
            s[0] = ne
        if ne > s[1]:
            s[1] = ne
    bar_cache: dict[tuple, list] = {}

    def _bars_for(contract, interval):
        key = (contract, interval)       # same contract can appear at multiple intervals
        if key not in bar_cache:
            lo, hi = node_span[contract]
            end = hi + dt.timedelta(days=fwd_days)
            start = lo - dt.timedelta(days=2)               # margin so the signal bar is in-window
            # interval-second granularity: slots in [start, end] is a safe UPPER bound on real
            # bars (markets < 24h), so this count guarantees full coverage; loader returns what exists.
            secs = _interval_seconds(interval)
            count = int((end - start).total_seconds() // secs) + 16
            bar_cache[key] = load_cn_window(contract, interval, count, end=end) or []
        return bar_cache[key]

    # collect forward paths per (horizon, population, instrument); account every drop
    coll: dict = {h: {"all": {}, "spec": {}} for h in horizons}
    skipped = {h: {"no_atr": 0, "no_bars": 0, "no_s0": 0, "short_horizon": 0} for h in horizons}
    for r in rows:
        inst = _instrument(r)
        contract = r.get("contract")
        interval = r.get("interval", "5min")
        node_end = dt.datetime.fromisoformat(r["ts_utc"])
        atr = (r.get("features_det") or {}).get("atr")
        bars = _bars_for(contract, interval) if contract else []
        for h in horizons:
            if not bars:
                skipped[h]["no_bars"] += 1
                continue
            p = _forward_path(bars, node_end, atr, h)
            if isinstance(p, str):
                skipped[h][p] += 1
                continue
            coll[h]["all"].setdefault(inst, []).append(p)
            if _is_spec(r):
                coll[h]["spec"].setdefault(inst, []).append(p)

    report = {
        "params": {"fwd_days": fwd_days, "horizons": horizons,
                   "right_k": RIGHT_K, "left_k": LEFT_K,
                   "note": "MFE/MAE/term in ATR units, long orientation, from signal-bar close"},
        "by_horizon": {},
    }
    report["coverage"] = {str(h): {"used": sum(len(v) for v in coll[h]["all"].values()),
                                   "skipped": skipped[h]} for h in horizons}
    for h in horizons:
        report["by_horizon"][str(h)] = {
            pop: {inst: _summ(paths) for inst, paths in sorted(coll[h][pop].items())}
            for pop in ("all", "spec")
        }
    return report


def _print(report: dict) -> None:
    print("=== Q2-Phase1: conditional forward-return tails (convexity) — au(precious) vs cu/rb(base) ===")
    print(f"params: {report['params']}")
    for h, cov in report.get("coverage", {}).items():
        print(f"coverage h={h}: used={cov['used']} skipped={cov['skipped']}")
    for h, pops in report["by_horizon"].items():
        print(f"\n----- horizon = {h} bars -----")
        for pop in ("all", "spec"):
            print(f"  [{pop}] population:")
            for inst, s in pops[pop].items():
                if s.get("n", 0) == 0:
                    continue
                rt = s["right_tail"]
                print(f"    {inst:<3} n={s['n']:>4} | term mean={s['term_mean']} skew={s['term_skew']} "
                      f"| MFE mean={s['mfe_mean']} (vol-dominated, ~symmetric)")
                print(f"        call_payoff(ATR) {s['call_payoff']} | put {s['put_payoff']} "
                      f"| call/put@k1={s['call_over_put_k1']}")
                print(f"        excursion right {rt} | left {s['left_tail']} "
                      f"| asym={s['asym_p_mfe2_over_mae2']}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", type=Path, required=True)
    ap.add_argument("--philosopher-src", type=Path, default=_DEFAULT_TP_SRC)
    ap.add_argument("--fwd-days", type=int, default=25)
    ap.add_argument("--horizons", type=int, nargs="+", default=[96, 288])
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    rep = analyze(args.corpus, args.philosopher_src,
                  fwd_days=args.fwd_days, horizons=args.horizons)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(rep, ensure_ascii=False, indent=2))
    _print(rep)


if __name__ == "__main__":
    main()
