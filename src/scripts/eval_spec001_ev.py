"""eval_spec001_ev.py — EV/edge evaluation harness for SPEC-001 (philosopher → researcher, kanban t_0da3b750).

SPEC-001 = PA wedge-completion second-entry breakout long
(doc: trade-philosopher/doc/pa-replication/specs/spec-001-wedge-breakout-long.md).

The philosopher replica (scripts/replay_cn.py) emits ORDERS (entry/stop/target/direction)
per node into runs/_replica/replay_*.json but records NO realized outcome. This harness
consumes those replay files, simulates each order's forward exit bar-by-bar (via the
philosopher cn_data 5min interface), and reports gross/net R, win-rate, and distribution
— the EV/edge side of the handoff.

**Exit convention (EXPLICIT — pending philosopher ratification).** The replica's per-order
`invalidation_condition` is free text, so EV requires a deterministic convention. We use:
  - Entry: stop order. Long → triggers on first forward bar with high >= entry; short →
    low <= entry. (Validated: rb2607 long triggers 2025-07-24 13:35, matching the spec.)
  - Pre-entry: pending order lives until triggered, max_wait_bars elapses, or data ends.
    NO pre-entry invalidation is modelled — this harness is EXIT-ENGINE-ONLY. NB for rb2607
    the pre-entry low hit 3334 (2025-07-23 14:25), BELOW the stop (3365) AND below the
    replica's own invalidation (3352), so under ANY pre-entry-invalidation rule that order
    would have been VOIDED. So --validate proves the exit engine reproduces the documented
    entry→target path, NOT that the pending order stayed faithfully valid. Whether to model
    pre-entry invalidation is an OPEN convention (flagged to philosopher); the current EV
    assumes none — possibly optimistic. (reviewer card t_9ef7dc76.)
  - Post-entry: intrabar stop/target; if both hit in one bar, STOP first (conservative).
  - Timeout: mark-to-close after max_hold_bars.
  - R = (exit - entry)/(entry - stop) for long; mirrored for short. Net subtracts cost_R.

All timestamps are UTC (replica node `end` == cn_data bar `ts_open`, both UTC epoch).

Usage:
  python3 scripts/eval_spec001_ev.py --replay <path-to-replay_*.json> [--direction 做多]
  python3 scripts/eval_spec001_ev.py --validate     # self-check on rb2607 (expects +2.0R)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
from pathlib import Path

# Bridge to the philosopher cn_data 5min interface (the sanctioned data entry point).
# Path.home() is NOT robust: under Hermes/Kanban worker profiles HOME resolves to e.g.
# /home/drwho1985/.hermes/profiles/reviewer/home, so a ~-based default fails and tests
# silently skip (reviewer cards t_a0af6bc4 / t_9ef7dc76). Resolve, in order: env TP_PA_SRC
# → repo-relative sibling (normal checkout) → real absolute path (detached worktrees /
# profile workers where HOME differs) → ~ legacy. Override with --philosopher-src.
def _resolve_tp_src() -> Path:
    import os
    cands = []
    env = os.environ.get("TP_PA_SRC")
    if env:
        cands.append(Path(env))
    strats = Path(__file__).resolve().parents[3]          # <...>/strats
    cands.append(strats / "trade-philosopher" / "src")
    cands.append(Path("/home/drwho1985/workspace/quant/strats/trade-philosopher/src"))
    cands.append(Path.home() / "workspace/quant/strats/trade-philosopher/src")
    for c in cands:
        if (c / "tp" / "pa" / "cn_data.py").exists():
            return c
    return cands[-3]   # repo-relative best guess for a sensible error message


_DEFAULT_TP_SRC = _resolve_tp_src()


def _load_cn_window(tp_src: Path):
    if str(tp_src) not in sys.path:
        sys.path.insert(0, str(tp_src))
    try:
        from tp.pa.cn_data import load_cn_window  # noqa: E402
    except Exception as e:  # pragma: no cover
        raise SystemExit(
            f"cannot import tp.pa.cn_data from {tp_src} ({e}); pass --philosopher-src")
    return load_cn_window


def _utc(ts: int) -> dt.datetime:
    return dt.datetime.utcfromtimestamp(ts)


def simulate_order(order: dict, bars: list[dict], *, node_end: dt.datetime,
                   max_wait_bars: int = 288, max_hold_bars: int = 288,
                   cost_r: float = 0.0) -> dict | None:
    """Forward-bar exit sim for one stop order. Returns dict with outcome + R, or None
    if entry never triggered within max_wait_bars. bars: chronological forward bars."""
    direction = order["order_direction"]            # 做多 / 做空
    entry = float(order["entry"])
    stop = float(order["stop"])
    target = float(order["target"])
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    is_long = direction == "做多"
    fwd = [b for b in bars if _utc(b["ts_open"]) > node_end]
    # --- entry ---
    entry_i = None
    for i, b in enumerate(fwd[:max_wait_bars]):
        if (is_long and b["high"] >= entry) or (not is_long and b["low"] <= entry):
            entry_i = i
            break
    if entry_i is None:
        # No trigger. If forward data ran out before the wait window elapsed we can't
        # know whether it would have triggered later → flag as unresolved, not a no-trade.
        exhausted = len(fwd) < max_wait_bars
        return {"triggered": False, "resolved": not exhausted,
                "exit_kind": "entry_data_exhausted" if exhausted else "no_trigger"}
    # --- exit ---
    held = fwd[entry_i: entry_i + max_hold_bars]
    exit_px = exit_kind = exit_ts = None
    for b in held:
        hit_stop = (b["low"] <= stop) if is_long else (b["high"] >= stop)
        hit_tgt = (b["high"] >= target) if is_long else (b["low"] <= target)
        if hit_stop:                      # conservative: stop first on same-bar ambiguity
            exit_px, exit_kind, exit_ts = stop, "stop", _utc(b["ts_open"])
            break
        if hit_tgt:
            exit_px, exit_kind, exit_ts = target, "target", _utc(b["ts_open"])
            break
    if exit_px is None:
        if len(held) >= max_hold_bars:    # genuine timeout → mark to close of last held bar
            exit_px, exit_kind, exit_ts = float(held[-1]["close"]), "timeout", _utc(held[-1]["ts_open"])
        else:                             # forward data ran out before max_hold → unresolved
            return {"triggered": True, "resolved": False, "exit_kind": "exit_data_exhausted",
                    "entry_ts": _utc(fwd[entry_i]["ts_open"]).isoformat(),
                    "bars_held": len(held)}
    gross_r = (exit_px - entry) / risk if is_long else (entry - exit_px) / risk
    return {
        "triggered": True, "resolved": True, "entry_ts": _utc(fwd[entry_i]["ts_open"]).isoformat(),
        "exit_ts": exit_ts.isoformat(), "exit_kind": exit_kind,
        "gross_r": round(gross_r, 4), "net_r": round(gross_r - cost_r, 4),
    }


def orders_from_replay(replay: dict, direction: str | None) -> list[dict]:
    out = []
    for r in replay.get("results", []):
        if r.get("order_type") in (None, "不下单") or not r.get("entry"):
            continue
        if direction and r.get("order_direction") != direction:
            continue
        out.append(r)
    return out


def evaluate(replay_paths: list[Path], *, direction: str | None, tp_src: Path,
             fwd_window: int, cost_r: float, max_wait_bars: int, max_hold_bars: int) -> dict:
    load_cn_window = _load_cn_window(tp_src)
    # load_cn_window returns the LAST n bars ending at `end`. To get the bars immediately
    # AFTER node_end (the forward horizon), the window must extend a bit past node_end in
    # calendar time AND carry enough bars to reach back to node_end — otherwise the tail
    # near a far-future `end` drops the post-signal bars (codex P2). We therefore set a
    # modest forward calendar margin and an n large enough to span it many times over,
    # then verify the loaded window actually reaches back to node_end (guard below).
    horizon_bars = max_wait_bars + max_hold_bars
    fwd_days = max(20, horizon_bars // 30)      # generous calendar cover for the horizon
    load_n = max(fwd_window, 8000)              # >> bars in fwd_days → window spans node_end
    rows = []
    for p in replay_paths:
        replay = json.loads(p.read_text())
        contract = replay["contract"]
        interval = replay.get("interval", "5min")
        for o in orders_from_replay(replay, direction):
            node_end = dt.datetime.fromisoformat(o["end"])
            bars = load_cn_window(contract, interval, load_n,
                                  end=node_end + dt.timedelta(days=fwd_days))
            # Guard: window must start at/before node_end, else the forward slice would be
            # mis-anchored (started after the signal) → cannot trust; mark unresolved.
            if not bars or _utc(bars[0]["ts_open"]) > node_end:
                rows.append({"contract": contract, "node_end": o["end"],
                             "direction": o.get("order_direction"), "triggered": False,
                             "resolved": False, "exit_kind": "window_misanchored"})
                continue
            sim = simulate_order(o, bars, node_end=node_end, cost_r=cost_r,
                                 max_wait_bars=max_wait_bars, max_hold_bars=max_hold_bars)
            if sim is None:
                continue
            rows.append({"contract": contract, "node_end": o["end"],
                         "cycle": o.get("cycle"), "direction": o.get("order_direction"),
                         "entry": o["entry"], "stop": o["stop"], "target": o["target"],
                         **sim})
    resolved = [r for r in rows if r.get("triggered") and r.get("resolved")]
    unresolved = [r for r in rows if not r.get("resolved")]
    grs = [r["gross_r"] for r in resolved]
    nrs = [r["net_r"] for r in resolved]
    return {
        "n_orders": len(rows),
        "n_resolved_trades": len(resolved),
        "n_unresolved": len(unresolved),   # data-exhausted entry/exit — EXCLUDED from EV
        "n_no_trigger": sum(1 for r in rows if r.get("exit_kind") == "no_trigger"),
        "win_rate": round(sum(1 for r in resolved if r["gross_r"] > 0) / len(resolved), 4) if resolved else None,
        "mean_gross_r": round(statistics.mean(grs), 4) if grs else None,
        "mean_net_r": round(statistics.mean(nrs), 4) if nrs else None,
        "median_gross_r": round(statistics.median(grs), 4) if grs else None,
        "exit_kinds": {k: sum(1 for r in resolved if r["exit_kind"] == k)
                       for k in ("target", "stop", "timeout")},
        "orders": rows,
        "caveat": ("EV is only meaningful at scale; current replica corpus is tiny "
                   "(N=1 SPEC-001 long). Convention pending philosopher ratification. "
                   "Unresolved (data-exhausted) trades are excluded from EV stats."),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--replay", type=Path, nargs="*", default=[])
    ap.add_argument("--direction", default="做多",
                    help="做多 (default; SPEC-001 is long-only) / 做空 / all")
    ap.add_argument("--philosopher-src", type=Path, default=_DEFAULT_TP_SRC)
    ap.add_argument("--fwd-window", type=int, default=600, help="bars to load per order")
    ap.add_argument("--cost-r", type=float, default=0.0, help="round-trip cost in R units")
    ap.add_argument("--max-wait-bars", type=int, default=288)
    ap.add_argument("--max-hold-bars", type=int, default=288)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--validate", action="store_true",
                    help="self-check on rb2607 first_order (expects gross +2.0R)")
    args = ap.parse_args()

    if args.validate:
        rep = Path(args.philosopher_src).parent / "runs/_replica/replay_rb2607_5min.json"
        out = evaluate([rep], direction="做多", tp_src=args.philosopher_src,
                       fwd_window=args.fwd_window, cost_r=0.0,
                       max_wait_bars=args.max_wait_bars, max_hold_bars=args.max_hold_bars)
        long_orders = [r for r in out["orders"]
                       if r["direction"] == "做多" and r.get("triggered") and r.get("resolved")]
        ok = any(abs(r["gross_r"] - 2.0) < 1e-6 and r["exit_kind"] == "target" for r in long_orders)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        print(f"\nVALIDATE rb2607 long == +2.0R target: {'PASS' if ok else 'FAIL'}")
        sys.exit(0 if ok else 1)

    direction = None if args.direction == "all" else args.direction
    out = evaluate(args.replay, direction=direction, tp_src=args.philosopher_src,
                   fwd_window=args.fwd_window, cost_r=args.cost_r,
                   max_wait_bars=args.max_wait_bars, max_hold_bars=args.max_hold_bars)
    txt = json.dumps(out, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(txt)
    print(txt)


if __name__ == "__main__":
    main()
