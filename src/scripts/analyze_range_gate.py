"""analyze_range_gate.py — range_vs_avg gate 阈值扫描 + walk-forward 验证（t_6c3f043a）。

t_ecb98b40 发现 range_vs_avg（信号棒过度延伸/棒长惩罚）是 bottom×opposing 上唯一
正交且显著的 Brooks 特征。本脚本补 productionize 前的验证关：把它当 gate filter
（drop range_vs_avg > cutoff = 剔除过度延伸的入场），验 (1) 阈值稳健性 (2) 时间外样本。

**机械评估器：只输出统计，不打 PASS/FAIL，不解读裁决。**

复用 analyze_signalbar_quality.run_symbol（已含 policy gate + range_vs_avg + realized_r
+ date 的 bottom×opposing 行），不重复管道。

输出：
1. 阈值扫描（full sample）：一组 cutoff 的 gated lane（保留 range_vs_avg<=cutoff）vs
   full lane EV + 保留率，画 EV(threshold) 曲线判单调性/最佳切点。
2. a-priori gate（Brooks cutoff=1.5）：gated vs dropped EV + gated vs full lane 提升，
   pooled + by-pool + bootstrap95（kept−dropped gap）。
3. walk-forward：按 date 时间序 K 折（默认 3，等数量 chronological）+ IS/OOS（按切分日），
   固定 cutoff=1.5 下每折 gated vs full EV，验 OOS 稳定（剔除过度延伸是否每折都不亏）。
4. Bonferroni 注记：阈值扫描含 len(GRID) 次比较，gap 的单点 p 需按 GRID 数校正。

Usage:
  uv run python scripts/analyze_range_gate.py --pools CN_BOND CN_METAL US_EQUITY \
      --out data/review/range_gate_validation.json
  # 无 uv 环境：python3 scripts/analyze_range_gate.py ...
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from data import bar_loader
from scripts.analyze_signalbar_quality import (
    POOL_INSTRUMENT_CLASS,
    POOLS,
    run_symbol,
)

GATE_CUTOFF = 1.5      # a-priori Brooks 过度延伸阈（棒长 > 1.5×近期均长 = 差）
EMPIRICAL_CUTOFF = 1.0  # 阈值扫描里 edge 最强且 OOS 稳定的经验切点（≈中位数）
GRID = (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)   # 阈值扫描
WF_CUTOFFS = (1.0, 1.25, 1.5)   # walk-forward 在多个 cutoff 上验 OOS 稳定（含强 edge 的 1.0）
K_FOLDS = 3            # chronological walk-forward 折数
IS_CUTOFF_DATE = "2025-06-30"   # IS <= 该日 < OOS（与 premium harness 同口径）
BOOTSTRAP_N = 10000
BOOTSTRAP_SEED = 42
DEFAULT_POOLS = ("CN_BOND", "CN_METAL", "US_EQUITY")


def _ev(rows: list[dict]) -> float | None:
    return round(float(np.mean([r["realized_r"] for r in rows])), 6) if rows else None


def _bootstrap_gap(a: list[float], b: list[float]) -> dict:
    """bootstrap mean(a)-mean(b) 95% CI + P(gap>0)。"""
    if not a or not b:
        return {"gap": None, "ci95": [None, None], "p_gt0": None}
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    aa, bb = np.asarray(a), np.asarray(b)
    d = [aa[rng.integers(0, len(aa), len(aa))].mean()
         - bb[rng.integers(0, len(bb), len(bb))].mean()
         for _ in range(BOOTSTRAP_N)]
    lo, hi = np.percentile(d, [2.5, 97.5])
    return {"gap": round(float(aa.mean() - bb.mean()), 6),
            "ci95": [round(float(lo), 6), round(float(hi), 6)],
            "p_gt0": round(float(np.mean(np.asarray(d) > 0)), 4)}


def threshold_sweep(rows: list[dict]) -> dict:
    """各 cutoff 的 gated lane（range_vs_avg<=cutoff）vs full lane。"""
    valid = [r for r in rows if np.isfinite(r["range_vs_avg"])]
    full_ev = _ev(valid)
    out = {}
    for c in GRID:
        kept = [r for r in valid if r["range_vs_avg"] <= c]
        dropped = [r for r in valid if r["range_vs_avg"] > c]
        out[f"cutoff_{c}"] = {
            "n_kept": len(kept), "keep_frac": round(len(kept) / len(valid), 4) if valid else None,
            "ev_kept": _ev(kept), "n_dropped": len(dropped), "ev_dropped": _ev(dropped),
            "lane_improvement": (round(_ev(kept) - full_ev, 6)
                                 if kept and full_ev is not None else None),
        }
    return {"full_lane_ev": full_ev, "n": len(valid), "by_cutoff": out}


def gate_split(rows: list[dict], cutoff: float) -> dict:
    valid = [r for r in rows if np.isfinite(r["range_vs_avg"])]
    kept = [r for r in valid if r["range_vs_avg"] <= cutoff]
    dropped = [r for r in valid if r["range_vs_avg"] > cutoff]
    return {
        "cutoff": cutoff, "n": len(valid),
        "kept": {"n": len(kept), "ev": _ev(kept)},
        "dropped": {"n": len(dropped), "ev": _ev(dropped)},
        "full_lane_ev": _ev(valid),
        "lane_improvement": (round(_ev(kept) - _ev(valid), 6)
                             if kept and valid else None),
        "kept_vs_dropped_bootstrap": _bootstrap_gap(
            [r["realized_r"] for r in kept], [r["realized_r"] for r in dropped]),
    }


def walk_forward(rows: list[dict], cutoff: float, k: int) -> dict:
    """时间序 K 折 + IS/OOS：每折 gated vs full EV（剔除过度延伸是否 OOS 稳定）。"""
    from datetime import date as _date
    valid = sorted((r for r in rows if np.isfinite(r["range_vs_avg"])),
                   key=lambda r: r["date"])
    n = len(valid)
    folds = {}
    for i in range(k):
        seg = valid[i * n // k:(i + 1) * n // k]
        kept = [r for r in seg if r["range_vs_avg"] <= cutoff]
        folds[f"F{i + 1}"] = {
            "n": len(seg), "date_range": [seg[0]["date"], seg[-1]["date"]] if seg else None,
            "full_ev": _ev(seg), "gated_ev": _ev(kept),
            "improvement": (round(_ev(kept) - _ev(seg), 6) if kept and seg else None),
        }
    cut = _date.fromisoformat(IS_CUTOFF_DATE)
    is_rows = [r for r in valid if _date.fromisoformat(r["date"]) <= cut]
    oos_rows = [r for r in valid if _date.fromisoformat(r["date"]) > cut]
    def _seg(seg):
        kept = [r for r in seg if r["range_vs_avg"] <= cutoff]
        return {"n": len(seg), "full_ev": _ev(seg), "gated_ev": _ev(kept),
                "improvement": (round(_ev(kept) - _ev(seg), 6) if kept and seg else None)}
    return {"k": k, "chronological_folds": folds,
            "is_oos": {"is_cutoff_date": IS_CUTOFF_DATE,
                       "is": _seg(is_rows), "oos": _seg(oos_rows)}}


def build_report(rows: list[dict], pools: list[str]) -> dict:
    by_pool_gate = {}
    for p in pools:
        prs = [r for r in rows if r.get("pool") == p]
        by_pool_gate[p] = gate_split(prs, GATE_CUTOFF) if prs else {"n": 0}
    return {
        "params": {
            "signal_population": "bottom × higher_relation=opposing (policy-gated)",
            "gate_def": "keep range_vs_avg <= cutoff (drop over-extended bars)",
            "gate_cutoff": GATE_CUTOFF, "sweep_grid": list(GRID),
            "k_folds": K_FOLDS, "is_cutoff_date": IS_CUTOFF_DATE,
            "bootstrap_n": BOOTSTRAP_N, "bootstrap_seed": BOOTSTRAP_SEED,
            "bonferroni_note": (f"threshold sweep = {len(GRID)} comparisons; "
                                f"single-point p must be corrected by {len(GRID)}×"),
            "note": "mechanical stats only; no PASS/FAIL", "pools": pools,
        },
        "n_events": len([r for r in rows if np.isfinite(r["range_vs_avg"])]),
        "threshold_sweep": threshold_sweep(rows),
        "gate_at_cutoff": gate_split(rows, GATE_CUTOFF),
        "gate_at_empirical_cutoff": gate_split(rows, EMPIRICAL_CUTOFF),
        "walk_forward": walk_forward(rows, GATE_CUTOFF, K_FOLDS),
        "walk_forward_by_cutoff": {
            f"cutoff_{c}": walk_forward(rows, c, K_FOLDS) for c in WF_CUTOFFS},
        "by_pool_gate": by_pool_gate,
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
    g = report["gate_at_cutoff"]
    print(f"wrote {args.out}  (n={report['n_events']} "
          f"gate@{GATE_CUTOFF}: kept {g['kept']['n']}/{g['kept']['ev']} "
          f"vs dropped {g['dropped']['n']}/{g['dropped']['ev']} "
          f"lane_improve={g['lane_improvement']})")


if __name__ == "__main__":
    main()
