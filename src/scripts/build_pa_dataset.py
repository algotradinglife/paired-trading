"""P0 — PA 推理链复刻标注数据集构建（确定性半段）。kanban t_6cf9f9c4

规范：doc/pa-annotation-dataset-spec-2026-06-14.md。本脚本交付 P0：
  候选闸门(detect_signals) + 出场仿真自动结果标(simulate_order) → §5 schema 每条候选决策点。
复用 researcher 参考实现（commit fd1f32eb/18ae0282）保证结果标 byte 一致：
  scripts.backtest_spec001_proxy.detect_signals / scripts.eval_spec001_ev.simulate_order。

P0 填确定性字段（无需人/LLM）：id/instrument/contract/interval/ts_utc/context_ref/
  features_det/candidate_source/outcome/liquidity/split/dedup_key。
P1 待 philosopher 复刻体补：decision/decision_trace/label_source(replica)/adjudication。

约定（写入 datasheet，§4）：
  tz：ts_open 与 node end 均 UTC epoch（_utc）。
  出场/失效：用 simulate_order 确定性约定（前向窗口、entry 在 max_wait_bars 内触发、
    同根 stop-first、max_hold_bars 超时、数据不足→unresolved 排除）。§4.2 入场前失效
    （自由文本，rb2607 3362 案例）属 decision 侧，待 philosopher 钉死，不影响 P0 结果标。
  无前视：features_det 仅用 bar i 及之前；outcome(look-ahead) 不进 features。
  端点：detect_signals 迭代 i∈[LOOKBACK, n-2]，窗口 ≤i。

用法：
  cd src && python3 scripts/build_pa_dataset.py --products rb --out data/review/pa_dataset_rb.jsonl
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.backtest_spec001_proxy import (  # noqa: E402
    ATR_PERIOD, LOOKBACK, detect_signals, _atr, _product,
)
from scripts.eval_spec001_ev import _DEFAULT_TP_SRC, _load_cn_window, simulate_order  # noqa: E402

MAX_WAIT = 288
MAX_HOLD = 288
COST_R = 0.0
INTERVAL = "5min"
CANDIDATE_SOURCE = "spec001_proxy.detect_signals"
LOAD_N = 200000   # load full contract history; context_ref reuses this for exact reload


def _features_det(bars: list[dict], i: int, sig: dict, atr: np.ndarray) -> dict:
    """No-lookahead deterministic features at bar i (uses ≤ i only)."""
    b = bars[i]
    o, h, lo, c = b["open"], b["high"], b["low"], b["close"]
    rng = h - lo
    a = float(atr[i])
    w0 = i - LOOKBACK + 1
    recent_ranges = [bars[j]["high"] - bars[j]["low"] for j in range(w0, i + 1)]
    avg_rng = float(np.mean(recent_ranges)) if recent_ranges else float("nan")
    return {
        "entry": sig["entry"], "stop": sig["stop"], "target": sig["target"],
        "payoff": sig["payoff"], "order_direction": sig["order_direction"],
        "atr": round(a, 6),
        "bar_range": round(rng, 6),
        "body_frac": round(abs(c - o) / rng, 6) if rng > 0 else None,
        "close_pos": round((c - lo) / rng, 6) if rng > 0 else None,
        "range_vs_avg": round(rng / avg_rng, 6) if avg_rng and avg_rng > 0 else None,
        "risk": round(sig["entry"] - sig["stop"], 6),
    }


def _id(contract: str, ts: dt.datetime) -> str:
    return f"{contract}-{INTERVAL}-{ts.strftime('%Y%m%dT%H%M%S')}"


def build(products: list[str], tp_src: Path) -> list[dict]:
    load_cn_window = _load_cn_window(tp_src)
    sys.path.insert(0, str(tp_src))
    from tp.pa.cn_data import list_contracts  # noqa: E402
    contracts = [c for c in list_contracts(INTERVAL) if _product(c) in set(products)]
    horizon = MAX_WAIT + MAX_HOLD
    recs: list[dict] = []
    seen: set = set()
    for ci, contract in enumerate(contracts):
        bars = load_cn_window(contract, INTERVAL, LOAD_N)
        if not bars or len(bars) < LOOKBACK + ATR_PERIOD + 2:
            continue
        prod = _product(contract)
        atr = _atr(bars)
        sigs = detect_signals(bars)
        kept = 0
        for s in sigs:
            i = s["i"]
            ts = s["ts"]
            key = (prod, ts.date())                      # cross-expiry dedup by product+day
            if key in seen:
                continue
            fwd = bars[i: i + horizon + 5]
            sim = simulate_order(s, fwd, node_end=ts, cost_r=COST_R,
                                 max_wait_bars=MAX_WAIT, max_hold_bars=MAX_HOLD)
            # Drop rows without a determinate outcome label: None (degenerate risk) and
            # *_data_exhausted (resolved=False, near contract data boundary). Keep resolved
            # rows incl no_trigger (a determinate "did-not-fill" label). codex P2 + spec §4.
            if sim is None or not sim.get("resolved"):
                continue
            seen.add(key)
            b = bars[i]
            recs.append({
                "id": _id(contract, ts),
                "instrument": prod, "contract": contract, "interval": INTERVAL,
                "ts_utc": ts.isoformat(),
                # Reload contract; full history up to end_ts is REQUIRED for exact features:
                # _atr is an EWM seeded at the contract's first bar, so atr[i] (hence all
                # ATR-derived fields) is path-dependent from bar 0. load_cn_window(n=LOAD_N,
                # end=end_ts) returns bars[0..i] (n >> contract length) → exact + no-lookahead
                # (end_ts excludes future). codex P2: a short bars_back window would NOT reproduce.
                "context_ref": {"loader": "tp.pa.cn_data.load_cn_window",
                                 "contract": contract, "interval": INTERVAL,
                                 "end_ts_utc": ts.isoformat(), "load_n": LOAD_N},
                "features_det": _features_det(bars, i, s, atr),
                "candidate_source": CANDIDATE_SOURCE,
                "decision": None,            # P1: 复刻体批标
                "decision_trace": None,      # P1: 复刻 decision_trace（逐节点）
                "label_source": "pending_replica",
                "adjudication": None,        # P2: 人工裁决尾部
                "outcome": {
                    "triggered": sim.get("triggered"), "resolved": sim.get("resolved"),
                    "exit_kind": sim.get("exit_kind"),
                    "gross_r": sim.get("gross_r"), "net_r": sim.get("net_r"),
                    "entry_ts": sim.get("entry_ts"), "exit_ts": sim.get("exit_ts"),
                },
                "liquidity": {"volume": b.get("volume"), "open_interest": b.get("open_interest")},
                "split": None,               # filled by _assign_splits
                "dedup_key": [prod, ts.date().isoformat()],
            })
            kept += 1
        print(f"  [{ci+1}/{len(contracts)}] {contract}: {len(sigs)} sigs, kept {kept} "
              f"(cum {len(recs)})", file=sys.stderr)
    return recs


def _assign_splits(recs: list[dict], train=0.70, val=0.15) -> dict:
    """Time-based split; boundaries on calendar date so no (product,day) straddles."""
    dates = sorted({r["ts_utc"][:10] for r in recs})
    if not dates:
        return {}
    n = len(dates)
    i_tr = int(n * train)
    i_va = int(n * (train + val))
    tr_end = dates[max(i_tr - 1, 0)]
    va_end = dates[max(i_va - 1, 0)]
    for r in recs:
        d = r["ts_utc"][:10]
        r["split"] = "train" if d <= tr_end else ("val" if d <= va_end else "test")
    return {"train_end": tr_end, "val_end": va_end,
            "n_dates": n, "first_date": dates[0], "last_date": dates[-1]}


def _resolved(recs):
    return [r for r in recs if r["outcome"]["triggered"] and r["outcome"]["resolved"]]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--products", nargs="+", default=["rb"])
    ap.add_argument("--out", type=Path, default=Path("data/review/pa_dataset_rb.jsonl"))
    ap.add_argument("--philosopher-src", type=Path, default=_DEFAULT_TP_SRC)
    args = ap.parse_args()

    recs = build(args.products, args.philosopher_src)
    split_info = _assign_splits(recs)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")

    # summary + gate EV (deterministic candidate gate; per-node trace EV is P1)
    res = _resolved(recs)
    gr = [r["outcome"]["gross_r"] for r in res]
    by_split = defaultdict(lambda: {"n": 0, "resolved": 0, "wins": 0, "sum_r": 0.0})
    for r in recs:
        s = by_split[r["split"]]
        s["n"] += 1
        if r in res:
            s["resolved"] += 1
            s["sum_r"] += r["outcome"]["gross_r"]
            if r["outcome"]["gross_r"] > 0:
                s["wins"] += 1
    summary = {
        "spec": "doc/pa-annotation-dataset-spec-2026-06-14.md", "phase": "P0",
        "products": args.products, "interval": INTERVAL,
        "candidate_source": CANDIDATE_SOURCE,
        "n_candidates": len(recs), "n_resolved": len(res),
        "win_rate": round(sum(1 for g in gr if g > 0) / len(gr), 4) if gr else None,
        "mean_gross_r": round(float(np.mean(gr)), 4) if gr else None,
        "exit_kinds": {k: sum(1 for r in res if r["outcome"]["exit_kind"] == k)
                       for k in ("target", "stop", "timeout")},
        "splits": {k: dict(v) for k, v in by_split.items()},
        "split_info": split_info,
        "sim_params": {"max_wait_bars": MAX_WAIT, "max_hold_bars": MAX_HOLD, "cost_r": COST_R},
    }
    with open(args.out.with_suffix(".summary.json"), "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
