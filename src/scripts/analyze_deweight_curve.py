"""analyze_deweight_curve.py — 连续 de-weight 曲线标定（P2.5, t_d257eb33）。

P2 综合设计建议用连续 de-weight（w_A × w_B）而非硬 AND（硬筛只留 11% 信号），但
Phase 1 只验了二值 cutoff。本卡标定连续权重的 EV-vs-feature 形状，对比三方案保信号量
优势，为 P3 备料。**机械统计 + 标定，不裁决；P3 接生产仍需 Hermes。**

复用 analyze_combined_gate.run_symbol（同一 bottom×opposing 事件群：range_vs_avg +
ordinal + realized_r + date，自包含、确定性）。

标定（无前视：权重函数只在 IS 上标定，再用于 OOS）：
- w_A(range_vs_avg)：分箱 EV → 单调降权。形如 clip((cut - rva)/scale + 1, w_min, 1)，
  rva ≤ cut 满权、越过度延伸权重越低（标定 cut/scale/w_min 见下）。
- w_B(ordinal)：首测满权，回踩按 EV 比降权（w_B = clip(ev_ord/ev_first, w_min, 1)）。
- w = w_A × w_B。

对比方案（同一事件群）：full（等权）/ 硬 AND（rva≤1.0 ∧ ord==1）/ 连续加权。
指标：weighted-EV = Σ(w·r)/Σw；有效 n = (Σw)² / Σw²（连续加权保信号量）。

Usage:
  uv run python scripts/analyze_deweight_curve.py --pools CN_BOND CN_METAL US_EQUITY \
      --out data/review/deweight_curve.json   # 无 uv 用 python3；CN_METAL/US 各数分钟
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from data import bar_loader
from scripts.analyze_combined_gate import run_symbol
from scripts.analyze_signalbar_quality import POOL_INSTRUMENT_CLASS, POOLS

# w_A 标定参数（range_vs_avg 连续降权）
WA_CUT = 1.0          # 拐点：rva ≤ 1.0 满权
WA_SCALE = 1.0        # 每超出 1.0×ATR 单位降权斜率
W_MIN = 0.2           # 权重下限（不完全归零，保留观测）
IS_CUTOFF_DATE = "2025-06-30"
BOOTSTRAP_N = 10000
BOOTSTRAP_SEED = 42
DEFAULT_POOLS = ("CN_BOND", "CN_METAL", "US_EQUITY")


def w_a(rva: float) -> float:
    """range_vs_avg 连续降权：rva≤WA_CUT 满权，越延伸越低，下限 W_MIN。"""
    if not np.isfinite(rva):
        return W_MIN
    return float(np.clip((WA_CUT - rva) / WA_SCALE + 1.0, W_MIN, 1.0))


def calibrate_w_b(rows: list[dict]) -> dict[int, float]:
    """w_B(ordinal)：首测满权，其余按 EV/EV(first) 比降权（下限 W_MIN）。
    只用传入 rows（调用方传 IS 行，避免前视）。"""
    by_ord: dict[int, list[float]] = {}
    for r in rows:
        by_ord.setdefault(min(r["ordinal"], 3), []).append(r["realized_r"])
    ev_first = float(np.mean(by_ord.get(1, [0.0]))) if by_ord.get(1) else 0.0
    out: dict[int, float] = {}
    for o, rs in by_ord.items():
        ev = float(np.mean(rs))
        if ev_first <= 0:
            out[o] = 1.0 if o == 1 else W_MIN
        else:
            out[o] = float(np.clip(ev / ev_first, W_MIN, 1.0))
    out.setdefault(1, 1.0)
    return out


def _wb(ordinal: int, wb_map: dict[int, float]) -> float:
    return wb_map.get(min(ordinal, 3), W_MIN)


def _weighted_ev(rows: list[dict], wfn) -> dict:
    """weighted-EV = Σ(w·r)/Σw；有效 n = (Σw)²/Σw²。"""
    if not rows:
        return {"n": 0, "weighted_ev": None, "eff_n": 0.0}
    w = np.array([wfn(r) for r in rows], dtype=float)
    r = np.array([r["realized_r"] for r in rows], dtype=float)
    sw = w.sum()
    eff_n = float(sw * sw / np.sum(w * w)) if np.sum(w * w) > 0 else 0.0
    return {"n": len(rows),
            "weighted_ev": round(float(np.sum(w * r) / sw), 6) if sw > 0 else None,
            "eff_n": round(eff_n, 1)}


def _ev(rows: list[dict]) -> float | None:
    return round(float(np.mean([r["realized_r"] for r in rows])), 6) if rows else None


def _bootstrap_weighted_gap(rows: list[dict], wfn) -> dict:
    """bootstrap(weighted-EV − equal-EV) 95% CI + P>0（同一 rows 重采样）。"""
    if len(rows) < 4:
        return {"gap": None, "ci95": [None, None], "p_gt0": None}
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    w = np.array([wfn(r) for r in rows])
    r = np.array([x["realized_r"] for x in rows])
    diffs = []
    for _ in range(BOOTSTRAP_N):
        idx = rng.integers(0, len(rows), len(rows))
        ww, rr = w[idx], r[idx]
        if ww.sum() <= 0:
            continue
        diffs.append(float(np.sum(ww * rr) / ww.sum() - rr.mean()))
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return {"gap": round(float(np.mean(diffs)), 6),
            "ci95": [round(float(lo), 6), round(float(hi), 6)],
            "p_gt0": round(float(np.mean(np.array(diffs) > 0)), 4)}


def build_report(rows: list[dict], pools: list[str]) -> dict:
    from datetime import date as _date
    valid = [r for r in rows if np.isfinite(r["range_vs_avg"])]

    # w_A 形状：range_vs_avg 五分位箱 EV
    rvas = sorted(r["range_vs_avg"] for r in valid)
    qs = np.quantile(rvas, [0, 0.2, 0.4, 0.6, 0.8, 1.0]) if rvas else []
    wa_bins = []
    for i in range(len(qs) - 1):
        lo, hi = qs[i], qs[i + 1]
        b = [r for r in valid if lo <= r["range_vs_avg"] <= hi] if i == len(qs) - 2 \
            else [r for r in valid if lo <= r["range_vs_avg"] < hi]
        wa_bins.append({"range": [round(float(lo), 3), round(float(hi), 3)],
                        "n": len(b), "ev": _ev(b),
                        "w_a_mid": round(w_a((lo + hi) / 2), 3)})

    # w_B 形状（full-sample，仅展示；标定用 IS）
    wb_full = calibrate_w_b(valid)
    ord_ev = {str(o): {"n": len([r for r in valid if min(r["ordinal"], 3) == o]),
                       "ev": _ev([r for r in valid if min(r["ordinal"], 3) == o]),
                       "w_b": round(wb_full.get(o, W_MIN), 3)}
              for o in (1, 2, 3)}

    # 三方案对比（full-sample，w_B 用 full 标定——OOS 段下面单独无前视标定）
    def wfn_full(r): return w_a(r["range_vs_avg"]) * _wb(r["ordinal"], wb_full)
    hard_and = [r for r in valid if r["range_vs_avg"] <= 1.0 and r["ordinal"] == 1]
    schemes = {
        "full_equal": {"n": len(valid), "ev": _ev(valid), "eff_n": len(valid)},
        "hard_AND_gate": {"n": len(hard_and), "ev": _ev(hard_and), "eff_n": len(hard_and)},
        "continuous_weight": _weighted_ev(valid, wfn_full),
    }
    boot = _bootstrap_weighted_gap(valid, wfn_full)

    # IS 标定 w_B → OOS 应用（无前视）
    cut = _date.fromisoformat(IS_CUTOFF_DATE)
    is_rows = [r for r in valid if _date.fromisoformat(r["date"]) <= cut]
    oos_rows = [r for r in valid if _date.fromisoformat(r["date"]) > cut]
    nested = {"applicable": False}
    if is_rows and oos_rows:
        wb_is = calibrate_w_b(is_rows)
        def wfn_is(r): return w_a(r["range_vs_avg"]) * _wb(r["ordinal"], wb_is)
        nested = {
            "applicable": True, "is_cutoff_date": IS_CUTOFF_DATE,
            "w_b_calibrated_on_is": {str(k): round(v, 3) for k, v in wb_is.items()},
            "oos_equal_ev": _ev(oos_rows),
            "oos_continuous": _weighted_ev(oos_rows, wfn_is),
            "oos_weighted_minus_equal": (
                round(_weighted_ev(oos_rows, wfn_is)["weighted_ev"] - _ev(oos_rows), 6)
                if oos_rows and _weighted_ev(oos_rows, wfn_is)["weighted_ev"] is not None
                else None),
        }
    return {
        "params": {
            "population": "bottom × opposing (raw)", "pools": pools,
            "w_a": f"clip((1.0 - rva)/{WA_SCALE} + 1, {W_MIN}, 1)",
            "w_b": "first full; else clip(ev_ord/ev_first, w_min, 1) (IS-calibrated)",
            "w": "w_a * w_b", "w_min": W_MIN, "is_cutoff_date": IS_CUTOFF_DATE,
            "note": "mechanical calibration; no PASS/FAIL; P3 needs Hermes",
        },
        "n": len(valid),
        "w_a_shape_quintiles": wa_bins,
        "w_b_shape_by_ordinal": ord_ev,
        "scheme_comparison": schemes,
        "continuous_vs_equal_bootstrap": boot,
        "nested_is_calibrate_oos_apply": nested,
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
    s = report["scheme_comparison"]
    print(f"wrote {args.out}  (n={report['n']} "
          f"full_ev={s['full_equal']['ev']} "
          f"hardAND_ev={s['hard_AND_gate']['ev']}(n={s['hard_AND_gate']['n']}) "
          f"cont_wev={s['continuous_weight']['weighted_ev']}(eff_n={s['continuous_weight']['eff_n']}))")


if __name__ == "__main__":
    main()
