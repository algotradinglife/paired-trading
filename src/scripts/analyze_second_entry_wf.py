"""analyze_second_entry_wf.py — second-entry 序数梯度 + 嵌套 walk-forward（t_c8aad725 / P1b）。

t_cf7cc3b8 在 bottom×opposing 信号群上发现"首测 > 二测+"（gap −0.42R, P=0.002），
但只过了单次 bootstrap，**没有 walk-forward**。本脚本给该发现补上 range_vs_avg 同款
out-of-sample 严格度：序数/阈值扫描 + 嵌套 train-select-test walk-forward。

**机械评估器：只输出统计，不打 PASS/FAIL，不解读裁决。**

复用 analyze_second_entry.run_symbol_second_entry 的行生成（bottom×opposing 事件 +
test_ordinal + realized_r + date + pool），不重新派生分类器（无前视：分类器锚定信号 bar，
只数信号前已确认的 swing low）。

输出：
1. 序数梯度（ordinal_gradient）：first（ord 1）/ 2nd+（ord>=2）/ 3rd+（ord>=3）的
   EV + win-rate(tp1_rate) + n，pooled + by-pool，附 first-vs-(2nd+) gap 的 bootstrap
   （10k, seed=42）。
2. 嵌套 walk-forward（nested_walk_forward）：按 IS_CUTOFF_DATE 分 IS/OOS；这里的 "gate" =
   只保留 first-tests（de-weight 2nd+ 的极端形态）。在 IS 上确认 first>2nd+ 提升方向，
   再用同一 gate 在 OOS 上评估，报 OOS lane_improvement + OOS bootstrap。镜像
   analyze_range_gate.nested_walk_forward 语义（空 IS/OOS 守卫 → applicable=False）。
3. 固定时间序 K=3 折（chronological_folds）：每折 first-vs-2nd+ EV gap（时间稳定性）。
4. Bonferroni 注记。

口径与运行时（hard-won）：
- bottom×opposing 过滤只用 higher_relation；analyze_second_entry 的 run 已含
  enrich_with_lower_tf（15min 全序富化是主成本，全池可能 >600s）。**按池跑是有界的复现路径**
  （CN_METAL 是 ~5min 主体）；逐品种 stderr 进度。
- 阈值/容差全用 ATR 相对（沿用 analyze_second_entry 的分类器，不引入固定价差 %）。
- 池异质：by-pool 单列（regime 不可移植）。
- 嵌套 WF 的 gate 只在 IS 上确认方向，OOS 仅评估，不窥 OOS 选规则。

Usage:
  uv run python scripts/analyze_second_entry_wf.py --pools CN_BOND CN_METAL US_EQUITY \
      --out data/review/second_entry_wf.json
  # 无 uv 环境：python3 scripts/analyze_second_entry_wf.py ...
  # 有界复现（单池，~5min）：... --pools CN_METAL
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from data import bar_loader
from scripts.analyze_second_entry import (
    POOL_INSTRUMENT_CLASS,
    POOLS,
    run_symbol_second_entry,
)

K_FOLDS = 3                       # chronological walk-forward 折数
IS_CUTOFF_DATE = "2025-06-30"     # IS <= 该日 < OOS（与 premium harness / range_gate 同口径）
BOOTSTRAP_N = 10000
BOOTSTRAP_SEED = 42
TP1_OUTCOMES = ("tp1_stop", "tp1_tp2", "tp1_max")
DEFAULT_POOLS = ("CN_BOND", "CN_METAL", "US_EQUITY")
# 嵌套 WF / 折分会重复用到 ordinal split，扫描的"序数 cutoff"：保留 ordinal <= c。
# c=1 即"只保留 first-tests"（核心 de-weight gate）；列出更宽的供 IS 选规则。
ORDINAL_GRID = (1, 2, 3)


def _ev(rows: list[dict]) -> float | None:
    return round(float(np.mean([r["realized_r"] for r in rows])), 6) if rows else None


def _win_rate(rows: list[dict]) -> float | None:
    if not rows:
        return None
    w = sum(1 for r in rows if r["outcome"] in TP1_OUTCOMES)
    return round(w / len(rows), 4)


def _group_stats(rows: list[dict]) -> dict:
    return {"n": len(rows), "ev": _ev(rows), "win_rate": _win_rate(rows)}


def _bootstrap_gap(a: list[float], b: list[float]) -> dict:
    """bootstrap mean(a)-mean(b) 95% CI + P(gap>0)（镜像 analyze_range_gate._bootstrap_gap）。"""
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


def _r(rows: list[dict]) -> list[float]:
    return [r["realized_r"] for r in rows]


def ordinal_gradient(rows: list[dict]) -> dict:
    """first(ord 1) / 2nd+(ord>=2) / 3rd+(ord>=3) 的 EV+win_rate+n，附 first-vs-(2nd+)
    gap bootstrap。"""
    first = [r for r in rows if r["ordinal"] == 1]
    second_plus = [r for r in rows if r["ordinal"] >= 2]
    third_plus = [r for r in rows if r["ordinal"] >= 3]
    return {
        "first": _group_stats(first),
        "second_plus": _group_stats(second_plus),
        "third_plus": _group_stats(third_plus),
        "first_vs_second_plus_bootstrap": _bootstrap_gap(
            _r(first), _r(second_plus)),
        "first_minus_second_plus_gap": (round(_ev(first) - _ev(second_plus), 6)
                                        if first and second_plus else None),
    }


def nested_walk_forward(rows: list[dict]) -> dict:
    """嵌套 train-select-test：按 IS_CUTOFF_DATE 分 IS/OOS。gate = 保留 ordinal<=c
    （de-weight 二测+）。在 IS 上扫 ORDINAL_GRID 选 lane_improvement 最大的 cutoff，
    再用该 cutoff 在 OOS 评估（cutoff 只用历史选，不看 OOS——无前视调参）。
    镜像 analyze_range_gate.nested_walk_forward 语义（空 IS/OOS → applicable=False）。"""
    from datetime import date as _date
    cut = _date.fromisoformat(IS_CUTOFF_DATE)
    is_rows = [r for r in rows if _date.fromisoformat(r["date"]) <= cut]
    oos_rows = [r for r in rows if _date.fromisoformat(r["date"]) > cut]
    if not is_rows or not oos_rows:
        return {"applicable": False, "reason": "IS or OOS empty"}
    is_full = _ev(is_rows)
    best_c, best_imp = None, None
    is_by_cutoff = {}
    for c in ORDINAL_GRID:
        kept = [r for r in is_rows if r["ordinal"] <= c]
        imp = (_ev(kept) - is_full) if kept and is_full is not None else None
        is_by_cutoff[c] = imp
        if imp is not None and (best_imp is None or imp > best_imp):
            best_c, best_imp = c, imp
    if best_c is None:
        return {"applicable": False, "reason": "no kept rows in IS for any cutoff"}
    oos_full = _ev(oos_rows)
    oos_kept = [r for r in oos_rows if r["ordinal"] <= best_c]
    oos_dropped = [r for r in oos_rows if r["ordinal"] > best_c]
    oos_imp = (_ev(oos_kept) - oos_full) if oos_kept and oos_full is not None else None
    return {
        "applicable": True, "is_cutoff_date": IS_CUTOFF_DATE,
        "gate_def": "keep ordinal <= cutoff (de-weight 2nd+ retests)",
        "is_selected_cutoff": best_c, "is_selected_improvement": round(best_imp, 6),
        "is_improvement_by_cutoff": {str(c): (round(v, 6) if v is not None else None)
                                     for c, v in is_by_cutoff.items()},
        "is_n": len(is_rows), "is_full_ev": is_full,
        "oos_n": len(oos_rows), "oos_full_ev": oos_full,
        "oos_kept_n": len(oos_kept), "oos_gated_ev": _ev(oos_kept),
        "oos_dropped_n": len(oos_dropped), "oos_dropped_ev": _ev(oos_dropped),
        "oos_improvement_at_selected_cutoff": (round(oos_imp, 6)
                                               if oos_imp is not None else None),
        "oos_kept_vs_dropped_bootstrap": _bootstrap_gap(
            _r(oos_kept), _r(oos_dropped)),
    }


def chronological_folds(rows: list[dict], k: int) -> dict:
    """固定时间序 K 折：每折 first(ord 1) vs 2nd+(ord>=2) EV gap（时间稳定性）。
    非嵌套——这里不在 train 上选规则，只切片报每折 gap。"""
    from datetime import date as _date
    valid = sorted(rows, key=lambda r: r["date"])
    n = len(valid)
    folds = {}
    for i in range(k):
        seg = valid[i * n // k:(i + 1) * n // k]
        first = [r for r in seg if r["ordinal"] == 1]
        sp = [r for r in seg if r["ordinal"] >= 2]
        gap = (round(_ev(first) - _ev(sp), 6) if first and sp else None)
        folds[f"F{i + 1}"] = {
            "n": len(seg),
            "date_range": [seg[0]["date"], seg[-1]["date"]] if seg else None,
            "first": _group_stats(first), "second_plus": _group_stats(sp),
            "first_minus_second_plus_gap": gap,
        }
    cut = _date.fromisoformat(IS_CUTOFF_DATE)
    is_rows = [r for r in valid if _date.fromisoformat(r["date"]) <= cut]
    oos_rows = [r for r in valid if _date.fromisoformat(r["date"]) > cut]

    def _seg(seg):
        first = [r for r in seg if r["ordinal"] == 1]
        sp = [r for r in seg if r["ordinal"] >= 2]
        return {"n": len(seg), "first": _group_stats(first),
                "second_plus": _group_stats(sp),
                "first_minus_second_plus_gap": (round(_ev(first) - _ev(sp), 6)
                                                if first and sp else None)}
    return {"k": k, "chronological_folds": folds,
            "is_oos": {"is_cutoff_date": IS_CUTOFF_DATE,
                       "is": _seg(is_rows), "oos": _seg(oos_rows)}}


def build_report(rows: list[dict], pools: list[str]) -> dict:
    by_pool = {}
    for p in pools:
        prs = [r for r in rows if r.get("pool") == p]
        by_pool[p] = (ordinal_gradient(prs) if prs else {"n": 0})
    return {
        "params": {
            "signal_population": "bottom × higher_relation=opposing",
            "ordinal_def": "1=first test; >=2=retest within tol_atr×ATR of a prior "
                           "swing low with >=bounce_atr×ATR intervening rally "
                           "(reused from analyze_second_entry classifier, no lookahead)",
            "gate_def": "keep ordinal <= cutoff (de-weight 2nd+ retests)",
            "ordinal_grid": list(ORDINAL_GRID),
            "k_folds": K_FOLDS, "is_cutoff_date": IS_CUTOFF_DATE,
            "bootstrap_n": BOOTSTRAP_N, "bootstrap_seed": BOOTSTRAP_SEED,
            "ev": "mean(realized_r)", "win_rate": "tp1_rate (any tp1 outcome)",
            "bonferroni_note": (f"ordinal sweep = {len(ORDINAL_GRID)} comparisons; "
                                f"first-vs-2nd+ single-point p must be corrected by "
                                f"{len(ORDINAL_GRID)}× when selecting cutoff"),
            "note": "mechanical stats only; no PASS/FAIL", "pools": pools,
        },
        "n_events": len(rows),
        "ordinal_histogram": {
            str(o): sum(1 for r in rows if r["ordinal"] == o)
            for o in sorted({r["ordinal"] for r in rows})
        },
        "ordinal_gradient": ordinal_gradient(rows),
        "nested_walk_forward": nested_walk_forward(rows),
        "chronological_folds": chronological_folds(rows, K_FOLDS),
        "by_pool": by_pool,
        "events": [{k: v for k, v in r.items() if not k.startswith("_")}
                   for r in rows],
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pools", nargs="+", default=list(DEFAULT_POOLS),
                    choices=sorted(POOLS))
    ap.add_argument("--apply-policy", action="store_true",
                    help="过生产 downstream policy gate（与 validated 口径一致，n 更小）")
    ap.add_argument("--quant-root", type=Path, default=bar_loader.DEFAULT_QUANT_ROOT)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    rows: list[dict] = []
    for pool in args.pools:
        icls = POOL_INSTRUMENT_CLASS[pool]
        for stem in POOLS[pool]:
            print(f"  scanning {pool}/{stem} ...", file=sys.stderr, flush=True)
            srows = run_symbol_second_entry(
                stem, icls, apply_policy_gate=args.apply_policy,
                quant_root=args.quant_root)
            for r in srows:
                r["pool"] = pool
            rows.extend(srows)

    report = build_report(rows, args.pools)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    g = report["ordinal_gradient"]
    nw = report["nested_walk_forward"]
    print(f"wrote {args.out}  (n={report['n_events']} "
          f"first n={g['first']['n']}/{g['first']['ev']} vs "
          f"2nd+ n={g['second_plus']['n']}/{g['second_plus']['ev']} "
          f"gap={g['first_minus_second_plus_gap']} | "
          f"WF applicable={nw.get('applicable')} "
          f"OOS_improve={nw.get('oos_improvement_at_selected_cutoff')})")


if __name__ == "__main__":
    main()
