"""analyze_overext_lanes.py — 过度延伸惩罚跨 lane 推广验证（P1a, kanban t_bd5f8b71）。

range_vs_avg（信号棒过度延伸/棒长惩罚）在 bottom×opposing 上过资格关
（t_6c3f043a：gate@1.0 gap +0.484R P=0.9998，OOS 方向稳）。本脚本验它是否**通用原则**：
在 direction × higher_relation 的多个 lane 上跑同一套 gate 验证（阈值扫描 + nested
walk-forward），看过度延伸惩罚是跨 lane 普遍成立、还是 bottom×opposing 特有。

**机械评估器：只输出统计，不打 PASS/FAIL，不解读裁决。**

效率：每 symbol 只 detect_signals + enrich_with_higher_tf 一次（运行时主导成本），
再按 (direction, higher_relation) 分桶到各 lane，逐信号按其方向 simulate_trade。
口径：原始信号群（未过 policy gate，最大化样本量、隔离过度延伸效应；与 P1a 验证
"惩罚是否存在"的目标一致——不论该 lane 现在是否被生产交易）。range_vs_avg 方向无关。

复用 analyze_range_gate 的聚合（threshold_sweep / gate_split / nested_walk_forward）
+ analyze_signalbar_quality 的 signal_bar_features。PA H2 lane（独立 detector）不在本卡，
作为 stretch 单列。

Usage:
  uv run python scripts/analyze_overext_lanes.py --pools CN_BOND CN_METAL US_EQUITY \
      --out data/review/overext_lanes.json   # 无 uv 用 python3；CN_METAL 是 ~5min 大头
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from data import bar_loader
from engine.divergence.multi_tf_context import enrich_with_higher_tf
from scripts.analyze_range_gate import (
    EMPIRICAL_CUTOFF,
    GATE_CUTOFF,
    gate_split,
    nested_walk_forward,
    threshold_sweep,
)
from scripts.analyze_signalbar_quality import (
    POOL_INSTRUMENT_CLASS,
    POOLS,
    WIN_OUTCOMES,
    _load_sym,
    compute_atr,
    detect_signals,
    load_bars,
    signal_bar_features,
    simulate_trade,
)
from scripts.analyze_signalbar_quality import DATA_DIR, STOP_MULT

# 验证的 lane = direction × higher_relation（bottom×opposing 是已验证基准对照）
LANES = (
    ("bottom", "opposing"), ("bottom", "supporting"), ("bottom", "neutral"),
    ("top", "opposing"), ("top", "supporting"), ("top", "neutral"),
)
DEFAULT_POOLS = ("CN_BOND", "CN_METAL", "US_EQUITY")


def run_symbol_all_lanes(stem: str, instrument_class: str,
                         quant_root: Path | None) -> list[dict]:
    """单 symbol：一次 detect+enrich，按 (direction, higher_relation) 分桶，
    逐信号按其方向 simulate。每行带 lane 标签 + range_vs_avg + realized_r + date。"""
    def _load_tf(suffix: str, level: str):
        df = _load_sym(stem, level, quant_root)
        if df is not None:
            return df
        p = DATA_DIR / f"{stem}_{suffix}.json"
        return load_bars(p) if p.exists() else None

    daily = _load_tf("daily", "D")
    sixty = _load_tf("60", "60min")
    fifteen = _load_tf("15", "15min")
    if any(x is None or x.empty for x in (daily, sixty, fifteen)):
        return []
    atr_series = compute_atr(daily)
    sigs = detect_signals(daily, instrument_class=instrument_class)
    ws = max(sixty["timestamp"].iloc[0], fifteen["timestamp"].iloc[0])
    we = min(sixty["timestamp"].iloc[-1], fifteen["timestamp"].iloc[-1])
    inw = [s for s in sigs
           if ws <= daily["timestamp"].iloc[s.candidate_bar_idx] <= we]
    en = enrich_with_higher_tf(inw, daily, sixty, higher_tf_level_id="1h")

    rows: list[dict] = []
    lane_set = {ln for ln in LANES}
    for sig in en:
        h_rel = (sig.multi_tf_context or {}).get("higher_relation")
        lane = (sig.direction, h_rel)
        if lane not in lane_set:
            continue
        idx = sig.candidate_bar_idx
        feat = signal_bar_features(daily, idx)
        if feat is None:
            continue
        sim = simulate_trade(daily, idx, sig.direction, STOP_MULT, atr_series)
        if sim is None:
            continue
        outcome, realized_r, _t, _e = sim
        rows.append({
            "symbol": stem, "pool": None,  # 由 main 填
            "date": sig.timestamp.strftime("%Y-%m-%d"),
            "direction": sig.direction, "higher_relation": h_rel,
            "lane": f"{sig.direction}x{h_rel}",
            "range_vs_avg": feat["range_vs_avg"],
            "outcome": outcome, "realized_r": round(float(realized_r), 6),
            "win": int(outcome in WIN_OUTCOMES),
        })
    return rows


def lane_report(rows: list[dict]) -> dict:
    """单 lane 的 gate 验证（复用 range_gate 聚合）。"""
    return {
        "n": len([r for r in rows if np.isfinite(r["range_vs_avg"])]),
        "full_lane_ev": (round(float(np.mean([r["realized_r"] for r in rows])), 6)
                         if rows else None),
        "threshold_sweep": threshold_sweep(rows),
        "gate_at_empirical_cutoff": gate_split(rows, EMPIRICAL_CUTOFF),
        "gate_at_brooks_cutoff": gate_split(rows, GATE_CUTOFF),
        "nested_walk_forward": nested_walk_forward(rows),
    }


def build_report(rows: list[dict], pools: list[str]) -> dict:
    by_lane = {}
    for d, h in LANES:
        lane = f"{d}x{h}"
        lr = [r for r in rows if r["lane"] == lane]
        by_lane[lane] = lane_report(lr)
    return {
        "params": {
            "feature": "range_vs_avg (signal-bar over-extension)",
            "lanes": [f"{d}x{h}" for d, h in LANES],
            "population": "raw per-lane signals (no policy gate)",
            "empirical_cutoff": EMPIRICAL_CUTOFF, "brooks_cutoff": GATE_CUTOFF,
            "note": "mechanical stats only; no PASS/FAIL", "pools": pools,
            "pa_h2_lane": "out of scope (separate detector); stretch",
        },
        "n_events_total": len(rows),
        "by_lane": by_lane,
        "events": rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pools", nargs="+", default=list(DEFAULT_POOLS),
                    choices=sorted(POOLS))
    ap.add_argument("--quant-root", type=Path, default=bar_loader.DEFAULT_QUANT_ROOT)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    rows: list[dict] = []
    for pool in args.pools:
        icls = POOL_INSTRUMENT_CLASS[pool]
        for stem in POOLS[pool]:
            print(f"  scanning {pool}/{stem} ...", file=sys.stderr, flush=True)
            for r in run_symbol_all_lanes(stem, icls, args.quant_root):
                r["pool"] = pool
                rows.append(r)

    report = build_report(rows, args.pools)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"wrote {args.out}  (n_total={report['n_events_total']})")
    for lane, lr in report["by_lane"].items():
        g = lr["gate_at_empirical_cutoff"]
        print(f"  {lane:18}: n={lr['n']:4} full_ev={lr['full_lane_ev']} "
              f"gate@1.0 gap={g['kept_vs_dropped_bootstrap']['gap']} "
              f"p={g['kept_vs_dropped_bootstrap']['p_gt0']}")


if __name__ == "__main__":
    main()
