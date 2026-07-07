"""analyze_second_entry.py — 二次入场分组 EV 验证（PA 假设 t_cf7cc3b8）。

Brooks 断言：第一次反转信号胜率 35-40%，第二次（双底二测 / 回踩前低）55-60%。
本脚本在已验证的 **bottom × h=opposing** 信号群上，把每个事件按"底部第一次
测试 vs 第二次+测试同一前低"分组，对比 EV/hit/full_stop。

**机械评估器：只输出统计，不打 PASS/FAIL，不解读裁决。**

复用已验证管道（不 fork backtest_rr_pool 逻辑）：
  detect_signals → enrich_with_higher_tf/lower_tf → simulate_trade（ATR 止损 +
  1R/2R 缩仓 + MAX_HOLD），EV = mean(realized_r)。

唯一新增：无前视的"测试序数"分类器（test_ordinal）：
  - 当前测试 = 信号 bar 自身的低 ref_low（codex P2：信号常在回踩低当根触发，
    该低尚未能确认为 swing；以"最近已确认 swing low"为锚会把真·二测误判成首测）。
  - 在 signal_idx 之前 lookback 根内，统计满足"双底二测"的、已确认的更早 swing low
    （confirm_idx = sl_idx + swing_n <= signal_idx，纯历史信息，无前视）：
    (a) 与 ref_low 价差 <= TOL_ATR × ATR（同一价位区，ATR 相对而非固定 %——
        债期整段波动 <2%，固定 % 容差会把所有事件误判成多次回踩）；
    (b) 该前低与 ref_low 之间存在 >= BOUNCE_ATR × ATR 的反弹（真·两腿结构，
        不是缓慢横向漂移）。
  - test_ordinal = 1 + 满足 (a)&(b) 的更早 swing low 数（1=首测，>=2=二测/回踩前低）。
  - 分组：first（序数 1） vs second+（序数 >=2）。

口径：默认在 **未过 downstream policy gate 的原始 bottom×opposing 群**上跑（最大化
样本量、隔离回踩效应）；--apply-policy 可切到生产门控群（与 validated 口径一致，n 更小）。

Usage:
  uv run python scripts/analyze_second_entry.py --pools CN_BOND CN_METAL US_EQUITY \
      --out data/review/second_entry_bottom_opp.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from data import bar_loader
from engine.divergence.downstream_policies import apply_policy
from engine.divergence.multi_tf_context import (
    enrich_with_higher_tf,
    enrich_with_lower_tf,
)
from engine.features.swing_context import detect_swing_points
from scripts.backtest_rr_pool import (
    POOL_INSTRUMENT_CLASS,
    POOLS,
    _load_sym,
    compute_atr,
    detect_signals,
    load_bars,
    simulate_trade,
)
from scripts.backtest_rr_pool import DATA_DIR

# --- 分类器参数（写死，输出到 JSON params）-------------------------------
SWING_N = 3            # detect_swing_points 两侧确认根数
TOL_ATR = 1.0         # 二测价位容差：|前低 - ref_low| <= 1.0×ATR 视为同一价位区
BOUNCE_ATR = 1.5      # 两低之间须有 >= 1.5×ATR 反弹（真·两腿结构）
LOOKBACK_BARS = 60    # 在 ref_low 之前回看多少根找更早的同位前低
STOP_MULT = 1.5       # ATR 止损倍数（与 validated 口径一致）
DEFAULT_POOLS = ("CN_BOND", "CN_METAL", "US_EQUITY")


def classify_test_ordinal(
    bars: pd.DataFrame,
    signal_idx: int,
    sl_idx: np.ndarray,
    atr_series: pd.Series,
    *,
    swing_n: int = SWING_N,
    tol_atr: float = TOL_ATR,
    bounce_atr: float = BOUNCE_ATR,
    lookback: int = LOOKBACK_BARS,
) -> dict | None:
    """信号 bar 的测试序数（无前视）。返回 {ordinal, ref_low, ref_low_idx,
    n_prior_same_level} 或 None（ATR 不可用）。

    **当前测试 = 信号 bar 自身的低**（codex P2：信号常在回踩低当根触发，该低
    尚未能确认为 swing；若以"最近已确认 swing low"为锚会把真·二测误判成首测）。
    锚 ref_low = bars.low[signal_idx]（信号当下即可知），再数信号前已确认的
    同位 swing low（confirm_idx = sl_idx + swing_n <= signal_idx，纯历史信息）。
    "同位"判定用 ATR 相对容差 + 中间反弹要求（见模块 docstring）。
    """
    atr = float(atr_series.iloc[signal_idx])
    if not np.isfinite(atr) or atr <= 0:
        return None
    ref_low = float(bars["low"].iloc[signal_idx])    # 当前测试 = 信号 bar 的低
    highs = bars["high"].values
    # 信号前已确认且在 lookback 内的更早 swing low（无前视）
    window_start = signal_idx - lookback
    priors = sl_idx[(sl_idx + swing_n <= signal_idx)
                    & (sl_idx < signal_idx) & (sl_idx >= window_start)]
    n_same = 0
    for p in priors:
        p = int(p)
        plow = float(bars["low"].iloc[p])
        if abs(plow - ref_low) > tol_atr * atr:
            continue                                  # 不在同一价位区
        # 两低之间（严格介于 p 与 signal_idx，不含信号 bar 自身）须有真实反弹
        # （codex P2：含信号 bar 高会让 outside/反转当根伪造"反弹"）
        between = highs[p + 1:signal_idx]
        if between.size == 0:
            continue                                  # 相邻两 bar，无中间反弹空间
        seg_high = float(np.max(between))
        if seg_high - max(plow, ref_low) >= bounce_atr * atr:
            n_same += 1
    return {
        "ordinal": 1 + n_same,
        "ref_low": round(ref_low, 6),
        "ref_low_idx": signal_idx,
        "n_prior_same_level": n_same,
    }


def run_symbol_second_entry(
    stem: str,
    instrument_class: str,
    *,
    apply_policy_gate: bool,
    quant_root: Path | None = None,
    swing_n: int = SWING_N,
    tol_atr: float = TOL_ATR,
    bounce_atr: float = BOUNCE_ATR,
    lookback: int = LOOKBACK_BARS,
) -> list[dict]:
    """单品种 bottom×opposing 事件 + 测试序数 + realized_r。镜像
    backtest_rr_pool.run_symbol 的检测/富化/模拟，仅附加 test_ordinal。"""
    def _load_tf(suffix: str, level: str) -> pd.DataFrame | None:
        df = _load_sym(stem, level, quant_root)
        if df is not None:
            return df
        p = DATA_DIR / f"{stem}_{suffix}.json"
        return load_bars(p) if p.exists() else None

    daily = _load_tf("daily", "D")
    sixty = _load_tf("60", "60min")
    fifteen = _load_tf("15", "15min")
    if daily is None or sixty is None or fifteen is None:
        return []
    if daily.empty or sixty.empty or fifteen.empty:
        return []

    atr_series = compute_atr(daily)
    _, sl_idx = detect_swing_points(daily, n=swing_n)

    sigs = detect_signals(daily, instrument_class=instrument_class)
    win_start = max(sixty["timestamp"].iloc[0], fifteen["timestamp"].iloc[0])
    win_end = min(sixty["timestamp"].iloc[-1], fifteen["timestamp"].iloc[-1])
    in_window = [s for s in sigs
                 if win_start <= daily["timestamp"].iloc[s.candidate_bar_idx] <= win_end]
    enriched = enrich_with_higher_tf(in_window, daily, sixty, higher_tf_level_id="1h")
    enriched = enrich_with_lower_tf(enriched, daily, fifteen, lower_tf_level_id="15m")

    rows: list[dict] = []
    for sig in enriched:
        if sig.direction != "bottom":
            continue
        ctx = sig.multi_tf_context or {}
        if ctx.get("higher_relation") != "opposing":
            continue
        if apply_policy_gate and apply_policy(
                sig, instrument_class=instrument_class).weight == 0.0:
            continue

        idx = sig.candidate_bar_idx
        cls = classify_test_ordinal(daily, idx, sl_idx, atr_series,
                                    swing_n=swing_n, tol_atr=tol_atr,
                                    bounce_atr=bounce_atr, lookback=lookback)
        if cls is None:
            continue   # ATR 不可用（极早期 bar）

        sim = simulate_trade(daily, idx, "bottom", STOP_MULT, atr_series)
        if sim is None:
            continue
        outcome, realized_r, _bars_tp1, _bars_exit = sim
        rows.append({
            "symbol": stem,
            "date": sig.timestamp.strftime("%Y-%m-%d"),
            "ordinal": cls["ordinal"],
            "group": "first" if cls["ordinal"] == 1 else "second+",
            "n_prior_same_level": cls["n_prior_same_level"],
            "confidence": round(float(sig.confidence), 4),
            "outcome": outcome,
            "realized_r": round(float(realized_r), 6),
        })
    return rows


def _group_stats(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0, "ev": None, "tp1_rate": None, "full_stop_rate": None}
    rs = [r["realized_r"] for r in rows]
    n = len(rs)
    tp1 = sum(1 for r in rows if r["outcome"] in ("tp1_stop", "tp1_tp2", "tp1_max"))
    fs = sum(1 for r in rows if r["outcome"] == "full_stop")
    return {
        "n": n,
        "ev": round(float(np.mean(rs)), 6),
        "tp1_rate": round(tp1 / n, 4),
        "full_stop_rate": round(fs / n, 4),
    }


def build_report(rows: list[dict], *, apply_policy_gate: bool,
                 pools: list[str]) -> dict:
    def split(rs):
        return {
            "first": _group_stats([r for r in rs if r["group"] == "first"]),
            "second+": _group_stats([r for r in rs if r["group"] == "second+"]),
        }

    by_pool = {}
    for pool in pools:
        prs = [r for r in rows if r["_pool"] == pool]
        by_pool[pool] = {"n": len(prs), **split(prs)}

    return {
        "params": {
            "signal_population": "bottom × higher_relation=opposing",
            "policy_gate_applied": apply_policy_gate,
            "swing_n": SWING_N, "tol_atr": TOL_ATR, "bounce_atr": BOUNCE_ATR,
            "lookback_bars": LOOKBACK_BARS,
            "stop_mult": STOP_MULT, "max_hold": "backtest_rr_pool.MAX_HOLD",
            "ordinal_def": "1=first test; >=2=retest within tol_atr×ATR of a prior "
                           "swing low with >=bounce_atr×ATR intervening rally",
            "ev": "mean(realized_r); realized_r per backtest_rr_pool outcomes",
            "pools": pools,
        },
        "n_events": len(rows),
        "pooled": split(rows),
        "by_pool": by_pool,
        "ordinal_histogram": {
            str(o): sum(1 for r in rows if r["ordinal"] == o)
            for o in sorted({r["ordinal"] for r in rows})
        },
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
    ap.add_argument("--quant-root", type=Path,
                    default=bar_loader.DEFAULT_QUANT_ROOT,
                    help="quant-data Parquet root（默认 data/quant/）")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    all_rows: list[dict] = []
    for pool in args.pools:
        icls = POOL_INSTRUMENT_CLASS[pool]
        for stem in POOLS[pool]:
            rows = run_symbol_second_entry(
                stem, icls, apply_policy_gate=args.apply_policy,
                quant_root=args.quant_root)
            for r in rows:
                r["_pool"] = pool
            all_rows.extend(rows)

    report = build_report(all_rows, apply_policy_gate=args.apply_policy,
                          pools=args.pools)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    p = report["pooled"]
    print(f"wrote {args.out}  (n={report['n_events']} "
          f"first n={p['first']['n']} ev={p['first']['ev']} | "
          f"second+ n={p['second+']['n']} ev={p['second+']['ev']})")


if __name__ == "__main__":
    main()
