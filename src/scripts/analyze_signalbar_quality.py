"""analyze_signalbar_quality.py — Brooks 信号棒质量特征增量（PA 假设 t_ecb98b40）。

已验证：swing tight/wick 双独立信号（底部 EMA↓×opp×(tight|wick) 高 hit）。
Brooks（文件16）信号棒质量给出更多同族特征：收盘近极点、实体/全幅比、棒长 ≤1.5×
近期均长（过长=过度延伸=差）。本脚本量化这些**相对已验证 tight/wick + 现有
bar_quality_bull 的增量**：是正交信息还是冗余。

**机械评估器：只输出统计，不打 PASS/FAIL，不解读裁决。**

复用已验证管道（不 fork backtest_rr_pool）：detect_signals → enrich → simulate_trade，
限 bottom × h=opposing（已验证子群）。win = outcome ∈ {tp1_stop, tp1_tp2, tp1_max}。

特征（信号 bar，无前视——均长窗口取信号前 LEN_WIN 根，不含信号 bar）：
  baseline（已验证）：tight=consol_ratio(range10/range20，<0.5 紧)、wick=wick_lo_ratio
  现有（已入 confidence）：bar_quality_bull = body_pct × close_pos
  Brooks 新：close_pos=(c−l)/range、body_pct=|c−o|/range、range_vs_avg=range/prior_avg_range
            not_overext = range_vs_avg ≤ 1.5

增量度量：
  1) 特征间 Pearson 相关（与 bar_quality_bull / tight / wick）——冗余度
  2) 每特征 上半 vs 下半（中位数切）win-rate / EV 差
  3) 条件增量：Brooks 长度规则 not_overext 在"已 good"信号内是否再抬 win-rate；
     Brooks 复合（close_pos 高 & body 高 & not_overext）相对 tight|wick baseline 的增量

Usage:
  uv run python scripts/analyze_signalbar_quality.py --pools CN_BOND CN_METAL US_EQUITY \
      --out data/review/signalbar_quality_bottom_opp.json
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
from scripts.backtest_rr_pool import (
    DATA_DIR,
    POOL_INSTRUMENT_CLASS,
    POOLS,
    _load_sym,
    compute_atr,
    detect_signals,
    load_bars,
    simulate_trade,
)

STOP_MULT = 1.5
LEN_WIN = 20          # 棒长基准：信号前 20 根均 range（无前视）
RANGE10, RANGE20 = 10, 20
OVEREXT_MULT = 1.5    # Brooks：棒长 > 1.5× 近期均长 = 过度延伸
WIN_OUTCOMES = ("tp1_stop", "tp1_tp2", "tp1_max")
# apply_policy 支持的 instrument_class（cn_bond 无策略规则——production 同样不在此层
# 门控；CN2 弱 sublevel 门控只针对 cn_futures/cn_metal_futures bottom×opposing）
_POLICY_CLASSES = {"us_equity", "cn_futures", "czce",
                   "cn_index_futures", "cn_metal_futures"}
DEFAULT_POOLS = ("CN_BOND", "CN_METAL", "US_EQUITY")
BOOTSTRAP_N = 10000
BOOTSTRAP_SEED = 42


def signal_bar_features(bars: pd.DataFrame, idx: int) -> dict | None:
    """信号 bar 的几何特征（无前视）。idx < RANGE20 或退化 bar 返回 None。"""
    if idx < RANGE20:
        return None
    o = float(bars["open"].iloc[idx])
    c = float(bars["close"].iloc[idx])
    h = float(bars["high"].iloc[idx])
    lo = float(bars["low"].iloc[idx])
    rng = h - lo
    if rng <= 0:
        return None
    body_pct = abs(c - o) / rng
    close_pos = (c - lo) / rng                       # 1=收在最高（bull 强收）
    wick_lo = (min(o, c) - lo) / rng
    highs = bars["high"].values
    lows = bars["low"].values
    hi10 = float(np.max(highs[idx - RANGE10 + 1:idx + 1]))
    lo10 = float(np.min(lows[idx - RANGE10 + 1:idx + 1]))
    hi20 = float(np.max(highs[idx - RANGE20 + 1:idx + 1]))
    lo20 = float(np.min(lows[idx - RANGE20 + 1:idx + 1]))
    consol_ratio = (hi10 - lo10) / ((hi20 - lo20) + 1e-9)   # tight: <0.5
    # 棒长 vs 信号前 LEN_WIN 根均 range（严格不含信号 bar，无前视）
    prior_ranges = (highs[idx - LEN_WIN:idx] - lows[idx - LEN_WIN:idx])
    avg_rng = float(np.mean(prior_ranges)) if prior_ranges.size else float("nan")
    range_vs_avg = rng / avg_rng if avg_rng and avg_rng > 0 else float("nan")
    return {
        "tight_consol": consol_ratio,          # 已验证
        "wick_lo": wick_lo,                     # 已验证
        "bar_quality_bull": body_pct * close_pos,   # 现有(入 confidence)
        "close_pos": close_pos,                 # Brooks 新
        "body_pct": body_pct,                   # Brooks 新
        "range_vs_avg": range_vs_avg,           # Brooks 新
        "not_overext": int(np.isfinite(range_vs_avg) and range_vs_avg <= OVEREXT_MULT),
    }


def run_symbol(stem: str, instrument_class: str,
               quant_root: Path | None) -> list[dict]:
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
    en = enrich_with_lower_tf(
        enrich_with_higher_tf(inw, daily, sixty, higher_tf_level_id="1h"),
        daily, fifteen, lower_tf_level_id="15m")
    rows: list[dict] = []
    for sig in en:
        if sig.direction != "bottom":
            continue
        if (sig.multi_tf_context or {}).get("higher_relation") != "opposing":
            continue
        # 生产 downstream policy gate（codex P2：与 backtest_rr_pool.run_symbol
        # 一致，剔除被禁用的 sublevel，使特征 EV 落在真·可交易管道上）。
        # cn_bond 无策略规则 → 不门控（与 production 一致）。
        if (instrument_class in _POLICY_CLASSES
                and apply_policy(sig, instrument_class=instrument_class).weight == 0.0):
            continue
        idx = sig.candidate_bar_idx
        feat = signal_bar_features(daily, idx)
        if feat is None:
            continue
        sim = simulate_trade(daily, idx, "bottom", STOP_MULT, atr_series)
        if sim is None:
            continue
        outcome, realized_r, _t, _e = sim
        rows.append({
            "symbol": stem, "date": sig.timestamp.strftime("%Y-%m-%d"),
            "outcome": outcome, "realized_r": round(float(realized_r), 6),
            "win": int(outcome in WIN_OUTCOMES), **feat,
        })
    return rows


def _bootstrap_diff(a: list[float], b: list[float]) -> dict:
    """bootstrap mean(a)-mean(b) 95% CI + P(diff>0)。a,b 为两组 realized_r。"""
    if not a or not b:
        return {"diff": None, "ci95": [None, None], "p_gt0": None}
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    aa, bb = np.asarray(a), np.asarray(b)
    d = [aa[rng.integers(0, len(aa), len(aa))].mean()
         - bb[rng.integers(0, len(bb), len(bb))].mean()
         for _ in range(BOOTSTRAP_N)]
    lo, hi = np.percentile(d, [2.5, 97.5])
    return {"diff": round(float(aa.mean() - bb.mean()), 6),
            "ci95": [round(float(lo), 6), round(float(hi), 6)],
            "p_gt0": round(float(np.mean(np.asarray(d) > 0)), 4)}


def _half_split(rows: list[dict], feat: str) -> dict:
    """按特征中位数切上/下半，报 win-rate / EV。"""
    vals = [r[feat] for r in rows if np.isfinite(r[feat])]
    if len(vals) < 4:
        return {"n": len(vals), "median": None}
    med = float(np.median(vals))
    hi = [r for r in rows if np.isfinite(r[feat]) and r[feat] > med]
    loo = [r for r in rows if np.isfinite(r[feat]) and r[feat] <= med]
    def wr(g): return round(np.mean([x["win"] for x in g]), 4) if g else None
    def ev(g): return round(np.mean([x["realized_r"] for x in g]), 6) if g else None
    return {
        "median": round(med, 6),
        "hi_half": {"n": len(hi), "win_rate": wr(hi), "ev": ev(hi)},
        "lo_half": {"n": len(loo), "win_rate": wr(loo), "ev": ev(loo)},
    }


FEATURES = ["tight_consol", "wick_lo", "bar_quality_bull",
            "close_pos", "body_pct", "range_vs_avg"]


def build_report(rows: list[dict], pools: list[str]) -> dict:
    n = len(rows)
    # 相关矩阵（冗余度）
    corr = {}
    if n >= 4:
        df = pd.DataFrame(rows)[FEATURES].apply(pd.to_numeric, errors="coerce")
        cm = df.corr(method="pearson").round(3)
        corr = {f: cm[f].to_dict() for f in FEATURES}
    # 每特征 上/下半
    per_feat = {f: _half_split(rows, f) for f in FEATURES}
    # 条件增量：Brooks 长度规则在"已 good（bar_quality_bull 上半）"内
    bq_vals = [r["bar_quality_bull"] for r in rows]
    bq_med = float(np.median(bq_vals)) if bq_vals else 0.0
    good = [r for r in rows if r["bar_quality_bull"] > bq_med]
    good_ext = [r for r in good if r["not_overext"] == 0]
    good_noext = [r for r in good if r["not_overext"] == 1]
    def grp(g): return {"n": len(g),
                        "win_rate": round(np.mean([x["win"] for x in g]), 4) if g else None,
                        "ev": round(np.mean([x["realized_r"] for x in g]), 6) if g else None}
    # Brooks 复合 vs tight|wick baseline（tight 用 <0.5 固定阈，wick 用中位数切）
    wick_med = float(np.median([r["wick_lo"] for r in rows])) if rows else 0.0
    cp_med = float(np.median([r["close_pos"] for r in rows])) if rows else 0.0
    bp_med = float(np.median([r["body_pct"] for r in rows])) if rows else 0.0
    baseline_good = [r for r in rows
                     if r["tight_consol"] < 0.5 or r["wick_lo"] > wick_med]
    brooks_good = [r for r in rows
                   if r["close_pos"] > cp_med and r["body_pct"] > bp_med
                   and r["not_overext"] == 1]
    both = [r for r in baseline_good
            if r["close_pos"] > cp_med and r["body_pct"] > bp_med
            and r["not_overext"] == 1]

    # 每池 range_vs_avg 上/下半 EV（codex P2：池级表自工件可复现，不靠重跑）
    by_pool = {}
    for p in pools:
        prs = [r for r in rows if r["pool"] == p]
        by_pool[p] = {"n": len(prs), "range_vs_avg_split": _half_split(prs, "range_vs_avg")}

    return {
        "params": {
            "signal_population": "bottom × higher_relation=opposing",
            "stop_mult": STOP_MULT, "len_win": LEN_WIN,
            "overext_mult": OVEREXT_MULT, "win_outcomes": list(WIN_OUTCOMES),
            "features": FEATURES,
            "note": "mechanical stats only; no PASS/FAIL", "pools": pools,
            "bootstrap_n": BOOTSTRAP_N, "bootstrap_seed": BOOTSTRAP_SEED,
        },
        "n_events": n,
        "overall_win_rate": round(np.mean([r["win"] for r in rows]), 4) if rows else None,
        "overall_ev": round(np.mean([r["realized_r"] for r in rows]), 6) if rows else None,
        "correlation_redundancy": corr,
        "per_feature_half_split": per_feat,
        "length_rule_increment_within_good_barquality": {
            "bar_quality_median": round(bq_med, 6),
            "good_and_not_overext": grp(good_noext),
            "good_but_overext": grp(good_ext),
            "ev_diff_bootstrap": _bootstrap_diff(
                [r["realized_r"] for r in good_noext],
                [r["realized_r"] for r in good_ext]),
        },
        "brooks_composite_vs_baseline": {
            "baseline_good(tight|wick)": grp(baseline_good),
            "brooks_good(close&body&not_overext)": grp(brooks_good),
            "both": grp(both),
        },
        "by_pool": by_pool,
        "events": rows,   # 保留 pool 标签（codex P2：池级表自工件可复现）
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
            for r in run_symbol(stem, icls, args.quant_root):
                r["pool"] = pool
                rows.append(r)

    report = build_report(rows, args.pools)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"wrote {args.out}  (n={report['n_events']} "
          f"win_rate={report['overall_win_rate']} ev={report['overall_ev']})")


if __name__ == "__main__":
    main()
