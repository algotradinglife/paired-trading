"""eval_spec001_corpus.py — FAITHFUL SPEC-001 EV on the philosopher replica corpus (t_0da3b750).

Consumes the §5-schema labelled corpus (philosopher commit, runs/_replica/pa_dataset_*.jsonl):
each record = candidate + replica `decision` (order/direction/entry/stop/target/win_rate_est)
+ embedded `outcome`. Unlike the deterministic proxy, these are the REPLICA's actual
faithful decisions — so this is the real SPEC-001 EV the handoff asked for.

Per philosopher's note: (1) re-run OUR simulate_order on the replica E/S/T independently
(don't just trust the embedded outcome — cross-check fidelity), (2) flag rollover-jump /
tiny-risk inflated R (the +277R artifact from the proxy) and report capped/robust EV.

SPEC-001 = breakout buy-stop LONG (order_type 突破单, direction 做多). Limit-long (限价单)
is a different entry type → reported separately, not in the headline SPEC-001 number.

Usage (corpus path auto-resolves from the philosopher sibling repo; no ~ — works under
Hermes/Kanban worker profiles where HOME differs. Override with --corpus / --philosopher-src):
  cd src && python3 scripts/eval_spec001_corpus.py --out data/review/spec001_faithful_ev.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from scripts.eval_spec001_ev import _DEFAULT_TP_SRC, _load_cn_window, _utc, simulate_order

SPEC_ORDER_TYPE = "突破单"          # SPEC-001 is a breakout (buy-stop) order
LONG = "做多"
ROLLOVER_FLAG_R = 10.0             # |gross_r| above this → flag as possible jump/tiny-risk artifact
BOOTSTRAP_N = 10000
BOOTSTRAP_SEED = 42


def _bootstrap_mean(grs: list[float]) -> dict:
    """Bootstrap 95% CI + P(mean>0) for the gross-R mean (reproducible, seed-pinned)."""
    if len(grs) < 4:
        return {"ci95": [None, None], "p_gt0": None}
    g = np.array(grs, float)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    means = g[rng.integers(0, len(g), (BOOTSTRAP_N, len(g)))].mean(axis=1)
    return {"ci95": [round(float(np.percentile(means, 2.5)), 4),
                     round(float(np.percentile(means, 97.5)), 4)],
            "p_gt0": round(float((means > 0).mean()), 4)}


def _decision_dir(d: dict) -> str | None:
    return d.get("order_direction") or d.get("direction")


def _order_from_decision(d: dict) -> dict | None:
    entry = d.get("entry", d.get("entry_price"))
    stop = d.get("stop", d.get("stop_loss_price"))
    target = d.get("target", d.get("take_profit_price"))
    if entry is None or stop is None or target is None:
        return None
    return {"order_direction": LONG, "entry": float(entry),
            "stop": float(stop), "target": float(target)}


def evaluate(corpus_path: Path, tp_src: Path, *, cost_r: float,
             fwd_days: int, max_wait_bars: int, max_hold_bars: int) -> dict:
    load_cn_window = _load_cn_window(tp_src)
    recs = [json.loads(ln) for ln in corpus_path.read_text().splitlines() if ln.strip()]
    spec, limit_long, other = [], [], []
    for r in recs:
        d = r.get("decision") or {}
        if not d.get("order") and d.get("order_type") in (None, "不下单"):
            continue
        ot, dirn = d.get("order_type"), _decision_dir(d)
        if ot == SPEC_ORDER_TYPE and dirn == LONG:
            spec.append(r)
        elif dirn == LONG:
            limit_long.append(r)
        else:
            other.append(r)

    rows = []
    for r in spec:
        d = r["decision"]
        order = _order_from_decision(d)
        if order is None:
            continue
        contract = r["contract"]
        node_end = dt.datetime.fromisoformat(r["ts_utc"])
        bars = load_cn_window(contract, r.get("interval", "5min"), 8000,
                              end=node_end + dt.timedelta(days=fwd_days))
        if not bars or _utc(bars[0]["ts_open"]) > node_end:
            rows.append({"id": r.get("id"), "contract": contract, "resolved": False,
                         "exit_kind": "window_misanchored"})
            continue
        sim = simulate_order(order, bars, node_end=node_end, cost_r=cost_r,
                             max_wait_bars=max_wait_bars, max_hold_bars=max_hold_bars)
        emb = r.get("outcome") or {}
        row = {"id": r.get("id"), "contract": contract, "ts": r["ts_utc"],
               "entry": order["entry"], "stop": order["stop"], "target": order["target"],
               "win_rate_est": d.get("win_rate_est"), "confidence": d.get("confidence"),
               **(sim or {"resolved": False, "exit_kind": "sim_none"}),
               "embedded_gross_r": emb.get("gross_r"),
               "embedded_exit_kind": emb.get("exit_kind")}
        # fidelity cross-check: our re-sim vs philosopher's embedded outcome
        if row.get("gross_r") is not None and emb.get("gross_r") is not None:
            row["matches_embedded"] = abs(row["gross_r"] - emb["gross_r"]) < 1e-3
        rows.append(row)

    return _summary(rows, spec, limit_long, other, cost_r)


def _stats(grs: list[float]) -> dict:
    if not grs:
        return {"n": 0}
    g = np.array(grs, float)
    return {
        "n": len(g), "win_rate": round(float((g > 0).mean()), 4),
        "mean_gross_r": round(float(g.mean()), 4), "median_gross_r": round(float(np.median(g)), 4),
        "winner_avg": round(float(g[g > 0].mean()), 4) if (g > 0).any() else None,
        "max_r": round(float(g.max()), 2), "min_r": round(float(g.min()), 2),
    }


def _summary(rows: list[dict], spec, limit_long, other, cost_r: float) -> dict:
    resolved = [r for r in rows if r.get("triggered") and r.get("resolved")]
    grs = [r["gross_r"] for r in resolved]
    # rollover-jump / tiny-risk artifact guard (philosopher caveat)
    flagged = [r for r in resolved if abs(r["gross_r"]) >= ROLLOVER_FLAG_R]
    g = np.array(grs, float) if grs else np.array([])
    capped5 = round(float(np.clip(g, -1, 5).mean()), 4) if grs else None
    excl_flagged = [x for r, x in zip(resolved, grs) if abs(x) < ROLLOVER_FLAG_R]
    mism = [r for r in resolved if r.get("matches_embedded") is False]
    return {
        "params": {
            "corpus": "philosopher replica labels (faithful, label_source=replica_*)",
            "spec_def": "突破单 + 做多 (breakout buy-stop long)",
            "cost_r": cost_r, "rollover_flag_r": ROLLOVER_FLAG_R,
            "note": "re-derived via our simulate_order on replica E/S/T; cross-checked vs embedded outcome",
        },
        "counts": {"spec_long_breakout": len(spec), "limit_long": len(limit_long),
                   "other_orders": len(other), "resolved": len(resolved)},
        "faithful_ev_spec_long": _stats(grs),
        "bootstrap_gross_ev": _bootstrap_mean(grs),
        "net_ev": {f"@{c}R": round(float((g - c).mean()), 4) for c in (0.1, 0.2, 0.3)} if grs else {},
        "robustness": {
            "ev_capped_at_5R": capped5,
            "ev_excl_flagged(|R|>=10)": round(float(np.mean(excl_flagged)), 4) if excl_flagged else None,
            "n_flagged_jump_or_tiny_risk": len(flagged),
            "flagged_ids": [r["id"] for r in flagged],
        },
        "fidelity_vs_embedded": {
            "n_compared": sum(1 for r in resolved if r.get("matches_embedded") is not None),
            "n_mismatch": len(mism), "mismatch_ids": [r["id"] for r in mism],
        },
        "exit_kinds": {k: sum(1 for r in resolved if r["exit_kind"] == k)
                       for k in ("target", "stop", "timeout")},
        "orders": rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", type=Path, default=None,
                    help="replica labels jsonl (default: derived from --philosopher-src sibling)")
    ap.add_argument("--philosopher-src", type=Path, default=_DEFAULT_TP_SRC)
    ap.add_argument("--cost-r", type=float, default=0.0)
    ap.add_argument("--fwd-days", type=int, default=25)
    ap.add_argument("--max-wait-bars", type=int, default=288)
    ap.add_argument("--max-hold-bars", type=int, default=288)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    # Corpus default FOLLOWS --philosopher-src (not the import-time sibling), so an explicit
    # override resolves the matching corpus (codex P2 on t_ac8a2d94).
    corpus = args.corpus or (args.philosopher_src.parent / "runs/_replica/pa_dataset_rb_claude.jsonl")
    rep = evaluate(corpus, args.philosopher_src, cost_r=args.cost_r, fwd_days=args.fwd_days,
                   max_wait_bars=args.max_wait_bars, max_hold_bars=args.max_hold_bars)
    txt = json.dumps(rep, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(txt)
    s = rep["faithful_ev_spec_long"]
    fid = rep["fidelity_vs_embedded"]
    rob = rep["robustness"]
    bs = rep["bootstrap_gross_ev"]
    print(f"SPEC-001 faithful EV (n={s.get('n')}): win={s.get('win_rate')} "
          f"gross={s.get('mean_gross_r')} median={s.get('median_gross_r')} max={s.get('max_r')} "
          f"CI={bs['ci95']} P(>0)={bs['p_gt0']}")
    print(f"  robustness: capped@5R={rob['ev_capped_at_5R']} excl-flagged={rob['ev_excl_flagged(|R|>=10)']} "
          f"(flagged {rob['n_flagged_jump_or_tiny_risk']})")
    print(f"  fidelity vs embedded: {fid['n_mismatch']} mismatches / {fid['n_compared']} compared")


if __name__ == "__main__":
    main()
