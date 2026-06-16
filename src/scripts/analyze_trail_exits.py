"""analyze_trail_exits.py — Card C (t_5af101b3): does a TRAIL exit lift the validated
SPEC-001/002/003 breakout winners, and does the STRUCTURED (swing) trail beat the mechanical
one while staying R002-compatible?

philosopher slice (per-contract, their sim, n≈106): baseline +0.502R, mechanical-trail(1R/1R)
+0.598R, structured-trail(swing3) +0.573R, structured-trail(swing5) +0.813R (+0.31R vs base).
This is the researcher EV/deployment-side INDEPENDENT cross-check in our own harness: same
breakout signals (replica-selected 突破单 from the labeled corpus), same per-contract bars via
the SANCTIONED loader (_load_cn_window — no data-store access), four exit policies on each
TRIGGERED long, four-method-same-set (only orders resolved under all four are compared so the
lift is apples-to-apples). Mechanical statistics, research; not PASS/FAIL. The R002/exit-
convention change is a fidelity/belief decision reserved for the user — this only quantifies.

Usage:
  cd src && ./.venv/bin/python scripts/analyze_trail_exits.py \
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
    _order_from_decision,
)
from scripts.eval_spec001_ev import _DEFAULT_TP_SRC, _load_cn_window, _utc

MAX_WAIT_BARS = 288
MAX_HOLD_BARS = 288
BOOTSTRAP_N = 5000
BOOTSTRAP_SEED = 12345


def _boot_ci(x: np.ndarray) -> list:
    if len(x) < 4:
        return [None, None]
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    m = x[rng.integers(0, len(x), (BOOTSTRAP_N, len(x)))].mean(axis=1)
    return [round(float(np.percentile(m, 2.5)), 3), round(float(np.percentile(m, 97.5)), 3)]


def _entry_index(fwd: list[dict], entry: float, is_long: bool):
    for i, b in enumerate(fwd[:MAX_WAIT_BARS]):
        if (is_long and b["high"] >= entry) or (not is_long and b["low"] <= entry):
            return i
    return None


def _r_of(exit_px, entry, risk, is_long):
    return (exit_px - entry) / risk if is_long else (entry - exit_px) / risk


def _exit_baseline(held, entry, stop, target, risk, is_long):
    """Replica's own OCO: stop or target, conservative stop-first on same-bar ambiguity."""
    for b in held:
        hit_stop = (b["low"] <= stop) if is_long else (b["high"] >= stop)
        hit_tgt = (b["high"] >= target) if is_long else (b["low"] <= target)
        if hit_stop:
            return _r_of(stop, entry, risk, is_long), "stop"
        if hit_tgt:
            return _r_of(target, entry, risk, is_long), "target"
    return _r_of(held[-1]["close"], entry, risk, is_long), "timeout"


def _exit_mech_trail(held, entry, stop, risk, is_long, start_r=1.0, dist_r=1.0):
    """Mechanical trail: once favourable excursion >= start_r*risk, ratchet the stop to
    (best favourable price -/+ dist_r*risk). No fixed target — let the winner run. Original
    stop applies until activation. Conservative: check the trailing/initial stop each bar."""
    trail = stop
    best = entry
    for b in held:
        # Conservative, look-ahead-free convention: check the stop against the PRIOR trail at
        # the bar open, THEN ratchet. A trail raised by THIS bar's high takes effect only from
        # the NEXT bar — we never assume the bar's high printed before its low (that would be an
        # optimistic intra-bar fill). This UNDERSTATES trail EV, so the measured lift is not an
        # artifact of same-bar look-ahead (codex flagged the same-bar recheck; deliberately not done).
        if (is_long and b["low"] <= trail) or (not is_long and b["high"] >= trail):
            return _r_of(trail, entry, risk, is_long), "trail_stop"
        best = max(best, b["high"]) if is_long else min(best, b["low"])
        fav = (best - entry) if is_long else (entry - best)
        if fav >= start_r * risk:
            cand = (best - dist_r * risk) if is_long else (best + dist_r * risk)
            trail = max(trail, cand) if is_long else min(trail, cand)
    return _r_of(held[-1]["close"], entry, risk, is_long), "timeout"


def _exit_struct_trail(held, entry, stop, risk, is_long, swing_n):
    """Structured trail (R002-compatible — follows price STRUCTURE, not a fixed R distance):
    ratchet the stop to the most recent CONFIRMED swing low (long) / high (short). A swing low
    at bar i is confirmed once swing_n bars on EACH side have lower-bounded it; confirmation is
    only available swing_n bars later (causal). Stop only ratchets in the favourable direction."""
    trail = stop
    n = swing_n
    for k, b in enumerate(held):
        if (is_long and b["low"] <= trail) or (not is_long and b["high"] >= trail):
            return _r_of(trail, entry, risk, is_long), "struct_stop"
        # a swing pivot centred at j is confirmable once k has advanced n bars past j
        j = k - n
        if j - n >= 0:
            lo = j - n
            hi = j + n  # inclusive window [j-n, j+n], all <= k so causal
            if is_long:
                piv = held[j]["low"]
                if piv == min(held[t]["low"] for t in range(lo, hi + 1)) and piv > trail:
                    trail = piv
            else:
                piv = held[j]["high"]
                if piv == max(held[t]["high"] for t in range(lo, hi + 1)) and piv < trail:
                    trail = piv
    return _r_of(held[-1]["close"], entry, risk, is_long), "timeout"


def _instrument(r: dict) -> str:
    return r.get("instrument") or "".join(
        c for c in (r.get("contract") or "") if not c.isdigit()) or "?"


def evaluate(corpus_path: Path, tp_src: Path, *, fwd_days: int) -> dict:
    load_cn_window = _load_cn_window(tp_src)
    rows = [json.loads(ln) for ln in Path(corpus_path).read_text().splitlines() if ln.strip()]
    methods = ("baseline", "mech_trail", "struct_trail3", "struct_trail5")
    per_inst: dict = {}
    n_signals = n_triggered = 0
    for r in rows:
        d = r.get("decision") or {}
        if not (d.get("order_type") == SPEC_ORDER_TYPE and _decision_dir(d) == LONG):
            continue
        order = _order_from_decision(d)
        if order is None:
            continue
        n_signals += 1
        contract = r.get("contract")
        interval = r.get("interval", "5min")
        node_end = dt.datetime.fromisoformat(r["ts_utc"])
        bars = load_cn_window(contract, interval, 8000,
                              end=node_end + dt.timedelta(days=fwd_days)) or []
        fwd = [b for b in bars if _utc(b["ts_open"]) > node_end]
        entry, stop, target = float(order["entry"]), float(order["stop"]), float(order["target"])
        risk = abs(entry - stop)
        is_long = order["order_direction"] == LONG
        if risk <= 0:
            continue
        ei = _entry_index(fwd, entry, is_long)
        if ei is None:
            continue
        held = fwd[ei: ei + MAX_HOLD_BARS]
        if len(held) < MAX_HOLD_BARS:        # need full window for all four methods (apples-to-apples)
            continue
        n_triggered += 1
        res = {
            "baseline": _exit_baseline(held, entry, stop, target, risk, is_long)[0],
            "mech_trail": _exit_mech_trail(held, entry, stop, risk, is_long)[0],
            "struct_trail3": _exit_struct_trail(held, entry, stop, risk, is_long, 3)[0],
            "struct_trail5": _exit_struct_trail(held, entry, stop, risk, is_long, 5)[0],
        }
        inst = _instrument(r)
        per_inst.setdefault(inst, {m: [] for m in methods})
        for m in methods:
            per_inst[inst][m].append(res[m])

    def _summ(rs):
        a = np.array(rs, float)
        return {"n": len(a), "ev": round(float(a.mean()), 4),
                "win": round(float((a > 0).mean()), 4), "ci": _boot_ci(a)} if len(a) else {"n": 0}

    pooled = {m: [] for m in methods}
    for inst, md in per_inst.items():
        for m in methods:
            pooled[m].extend(md[m])
    return {
        "params": {"max_hold_bars": MAX_HOLD_BARS, "fwd_days": fwd_days,
                   "methods": methods, "note": "four-method same-set; per-contract via sanctioned loader"},
        "n_spec_long_signals": n_signals, "n_resolved_all_four": n_triggered,
        "pooled": {m: _summ(pooled[m]) for m in methods},
        "by_instrument": {inst: {m: _summ(md[m]) for m in methods}
                          for inst, md in sorted(per_inst.items())},
    }


def _print(rep: dict) -> None:
    print("=== Card C: trail-exit EV on validated SPEC breakout-long (independent cross-check) ===")
    print(f"params: {rep['params']}")
    print(f"signals={rep['n_spec_long_signals']}  resolved-all-four (same set)={rep['n_resolved_all_four']}")
    if not rep["pooled"]["baseline"].get("n"):
        print("  (no breakout-long trades resolved under all four methods — nothing to compare)")
        return
    base = rep["pooled"]["baseline"]["ev"]
    print(f"\n  POOLED (n={rep['pooled']['baseline']['n']}):")
    for m, s in rep["pooled"].items():
        if s.get("n"):
            dv = round(s["ev"] - base, 4)
            print(f"    {m:<14} EV={s['ev']:+.4f} win={s['win']} CI={s['ci']} | vs baseline {dv:+.4f}")
    for inst, md in rep["by_instrument"].items():
        b = md["baseline"].get("ev")
        cells = " ".join(f"{m.replace('struct_trail','s'):>8}={md[m]['ev']:+.3f}"
                         for m in rep["params"]["methods"] if md[m].get("n"))
        print(f"  {inst} (n={md['baseline'].get('n')}): {cells}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", type=Path, required=True)
    ap.add_argument("--philosopher-src", type=Path, default=_DEFAULT_TP_SRC)
    ap.add_argument("--fwd-days", type=int, default=25)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    rep = evaluate(args.corpus, args.philosopher_src, fwd_days=args.fwd_days)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(rep, ensure_ascii=False, indent=2))
    _print(rep)


if __name__ == "__main__":
    main()
