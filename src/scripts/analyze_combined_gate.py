"""analyze_combined_gate.py — 综合 gate 设计：两个验过的 gate 是否叠加（P2, t_6fe02de5）。

Phase 1 给出两个 bottom×opposing 上验过的 gate：
- A 过度延伸惩罚（P1a/t_6c3f043a）：keep range_vs_avg ≤ 1.0（剔过度延伸信号棒）
- B 二次入场偏好（P1b/t_c8aad725）：keep ordinal == 1（首测，de-weight 回踩二测）

本卡综合：在**同一 bottom×opposing 事件群**上同时算 range_vs_avg + 测试序数，量化
A、B 单独 vs 组合（A∧B）的 EV/n，看两者是**正交叠加**还是**冗余重叠**——为 P3
productionize 的 gate 规格提供依据。

**机械评估器：只输出统计，不打 PASS/FAIL，不解读裁决。** P3（接 policy/confidence）
需 Hermes 对 de-weight 决策签字，本卡仅出设计依据。

复用：signal_bar_features（range_vs_avg）+ analyze_second_entry.classify_test_ordinal
（无前视序数）+ analyze_signalbar_quality 管道。一次 detect+enrich/symbol。

Usage:
  uv run python scripts/analyze_combined_gate.py --pools CN_BOND CN_METAL US_EQUITY \
      --out data/review/combined_gate.json   # 无 uv 用 python3
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
from engine.features.swing_context import detect_swing_points
from scripts.analyze_range_gate import EMPIRICAL_CUTOFF, _bootstrap_gap
from scripts.analyze_second_entry import classify_test_ordinal
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

SWING_N = 3
DEFAULT_POOLS = ("CN_BOND", "CN_METAL", "US_EQUITY")


def run_symbol(stem: str, instrument_class: str,
               quant_root: Path | None) -> list[dict]:
    """bottom×opposing 事件：每行带 range_vs_avg + ordinal + realized_r + date。"""
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
    _, sl_idx = detect_swing_points(daily, n=SWING_N)
    sigs = detect_signals(daily, instrument_class=instrument_class)
    ws = max(sixty["timestamp"].iloc[0], fifteen["timestamp"].iloc[0])
    we = min(sixty["timestamp"].iloc[-1], fifteen["timestamp"].iloc[-1])
    inw = [s for s in sigs
           if ws <= daily["timestamp"].iloc[s.candidate_bar_idx] <= we]
    en = enrich_with_higher_tf(inw, daily, sixty, higher_tf_level_id="1h")

    rows: list[dict] = []
    for sig in en:
        if sig.direction != "bottom":
            continue
        if (sig.multi_tf_context or {}).get("higher_relation") != "opposing":
            continue
        idx = sig.candidate_bar_idx
        feat = signal_bar_features(daily, idx)
        cls = classify_test_ordinal(daily, idx, sl_idx, atr_series)
        if feat is None or cls is None:
            continue
        sim = simulate_trade(daily, idx, "bottom", STOP_MULT, atr_series)
        if sim is None:
            continue
        outcome, realized_r, _t, _e = sim
        rows.append({
            "symbol": stem, "date": sig.timestamp.strftime("%Y-%m-%d"),
            "range_vs_avg": feat["range_vs_avg"], "ordinal": cls["ordinal"],
            "realized_r": round(float(realized_r), 6),
            "win": int(outcome in WIN_OUTCOMES),
        })
    return rows


def _cell(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0, "ev": None, "win_rate": None}
    return {"n": len(rows),
            "ev": round(float(np.mean([r["realized_r"] for r in rows])), 6),
            "win_rate": round(float(np.mean([r["win"] for r in rows])), 4)}


def build_report(rows: list[dict], pools: list[str]) -> dict:
    valid = [r for r in rows if np.isfinite(r["range_vs_avg"])]
    def not_overext(r): return r["range_vs_avg"] <= EMPIRICAL_CUTOFF
    def first(r): return r["ordinal"] == 1

    full = valid
    gate_a = [r for r in valid if not_overext(r)]              # over-ext gate
    gate_b = [r for r in valid if first(r)]                    # first-test gate
    both = [r for r in valid if not_overext(r) and first(r)]   # A ∧ B
    # 2x2 列联：看 A、B 是否正交（首测里 over-ext 占比 vs 全样本）
    contingency = {
        "first_and_not_overext": len(both),
        "first_and_overext": len([r for r in valid if first(r) and not not_overext(r)]),
        "retest_and_not_overext": len([r for r in valid if not first(r) and not_overext(r)]),
        "retest_and_overext": len([r for r in valid if not first(r) and not not_overext(r)]),
    }
    return {
        "params": {
            "population": "bottom × opposing (raw, no policy gate)",
            "gate_A": f"over-extension: keep range_vs_avg <= {EMPIRICAL_CUTOFF}",
            "gate_B": "second-entry: keep ordinal == 1 (first test)",
            "note": "mechanical stats only; no PASS/FAIL; P3 productionize needs Hermes",
            "pools": pools,
        },
        "n": len(valid),
        "cells": {
            "full": _cell(full),
            "gate_A_overext_only": _cell(gate_a),
            "gate_B_first_only": _cell(gate_b),
            "both_A_and_B": _cell(both),
        },
        "lane_improvement_vs_full": {
            "A_only": (round(_cell(gate_a)["ev"] - _cell(full)["ev"], 6)
                       if gate_a and full else None),
            "B_only": (round(_cell(gate_b)["ev"] - _cell(full)["ev"], 6)
                       if gate_b and full else None),
            "both": (round(_cell(both)["ev"] - _cell(full)["ev"], 6)
                     if both and full else None),
        },
        "marginal": {
            "both_minus_A": (round(_cell(both)["ev"] - _cell(gate_a)["ev"], 6)
                             if both and gate_a else None),
            "both_minus_B": (round(_cell(both)["ev"] - _cell(gate_b)["ev"], 6)
                             if both and gate_b else None),
        },
        "both_vs_full_bootstrap": _bootstrap_gap(
            [r["realized_r"] for r in both], [r["realized_r"] for r in full]),
        "contingency_2x2": contingency,
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
            for r in run_symbol(stem, icls, args.quant_root):
                r["pool"] = pool
                rows.append(r)

    report = build_report(rows, args.pools)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    c = report["cells"]
    print(f"wrote {args.out}  (n={report['n']} "
          f"full={c['full']['ev']} A={c['gate_A_overext_only']['ev']} "
          f"B={c['gate_B_first_only']['ev']} both={c['both_A_and_B']['ev']})")


if __name__ == "__main__":
    main()
