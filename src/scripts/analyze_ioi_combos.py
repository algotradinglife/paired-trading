"""analyze_ioi_combos.py — inside/outside/ioi 蜡烛组合的机械统计探针（PA 假设 t_26f5a08c）。

探索 inside bar / outside bar / ioi（inside→outside→inside 三根组合，breakout-pending）
作为候选 detector 信号的价值：(a) 这些组合在日线上多频繁出现，(b) 出现后的前向 EV。

**机械评估器：只输出统计，不打 PASS/FAIL，不解读裁决。** 这是探索性探针。

标准 PA 定义（全部无前视，仅用到 t 及之前的 bar）：
  - inside bar:  high[t] <= high[t-1] AND low[t] >= low[t-1]
  - outside bar: high[t] >= high[t-1] AND low[t] <= low[t-1]
  - ioi:         inside(t-2) → outside(t-1) → inside(t)  三根组合（在 t 当根确认）

前向结果度量（两套，均无前视）：
  1) **forward_atr_return（主度量，pure candle 用）**：(close[t+k] - close[t]) / ATR[t]，
     k ∈ {5, 10, 20}。candle 组合本身无方向，简单前向 ATR 归一化收益最干净、
     无方向假设；ATR 相对而非固定 %（债期整段波动 <2%，固定 % 度量在债上失真）。
     端点处理：仅当 t+k < len(bars) 才计入（窗口右端越界则丢弃，不补 NaN、不前视）。
  2) **simulate_trade_bottom（辅助度量，breakout/bottom 语境）**：复用
     backtest_rr_pool.simulate_trade，direction="bottom"，在组合 bar 收盘进场，
     ATR×1.5 止损、1R/2R 缩仓、MAX_HOLD。EV = mean(realized_r)。仅作 bottom 语境
     的方向化对照（组合本身方向不明，故标为辅助）。

bottom×opposing 共现：用 backtest_rr_pool.detect_signals + enrich_with_higher_tf
判定组合 bar 是否同时命中已验证的 bottom × higher_relation=opposing 信号；分
standalone（仅组合）vs coincident（组合 ∧ bottom×opposing）两组对比。

Bootstrap：10000 resample、seed=42，对 forward_atr_return(k=10) 与
simulate_trade EV 给 95% CI（pooled + by-pool）。

Usage:
  uv run python scripts/analyze_ioi_combos.py --pools CN_BOND CN_METAL US_EQUITY \
      --out data/review/ioi_combos.json
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
from engine.divergence.multi_tf_context import enrich_with_higher_tf
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

# --- 参数（写死，输出到 JSON params）-------------------------------------
FORWARD_KS = (5, 10, 20)   # 前向 ATR 归一化收益的 horizon
STOP_MULT = 1.5            # simulate_trade 辅助度量的 ATR 止损倍数
BOOTSTRAP_N = 10000
BOOTSTRAP_SEED = 42
CI_K = 10                  # bootstrap CI 取哪个 forward_atr_return horizon
DEFAULT_POOLS = ("CN_BOND", "CN_METAL", "US_EQUITY")
PATTERN_TYPES = ("inside", "outside", "ioi")


# ---------------------------------------------------------------------------
# Pure pattern detection (no lookahead — each flag at t uses only bars <= t)
# ---------------------------------------------------------------------------

def is_inside_bar(high: np.ndarray, low: np.ndarray, t: int) -> bool:
    """inside bar at t: high[t] <= high[t-1] AND low[t] >= low[t-1]. No lookahead."""
    if t < 1:
        return False
    return bool(high[t] <= high[t - 1] and low[t] >= low[t - 1])


def is_outside_bar(high: np.ndarray, low: np.ndarray, t: int) -> bool:
    """outside bar at t: high[t] >= high[t-1] AND low[t] <= low[t-1]. No lookahead."""
    if t < 1:
        return False
    return bool(high[t] >= high[t - 1] and low[t] <= low[t - 1])


def is_ioi(high: np.ndarray, low: np.ndarray, t: int) -> bool:
    """ioi at t: inside(t-2) → outside(t-1) → inside(t). Confirmed on bar t.

    No lookahead — uses only bars t-2, t-1, t (and their predecessors for the
    inside/outside checks, i.e. up to t-3). Returns False near the left edge.
    """
    if t < 3:
        return False
    return (
        is_inside_bar(high, low, t - 2)
        and is_outside_bar(high, low, t - 1)
        and is_inside_bar(high, low, t)
    )


def flag_patterns(bars: pd.DataFrame) -> dict[str, np.ndarray]:
    """Boolean arrays (len == len(bars)) for each pattern type. No lookahead."""
    high = bars["high"].to_numpy(dtype=float)
    low = bars["low"].to_numpy(dtype=float)
    n = len(bars)
    inside = np.zeros(n, dtype=bool)
    outside = np.zeros(n, dtype=bool)
    ioi = np.zeros(n, dtype=bool)
    for t in range(n):
        inside[t] = is_inside_bar(high, low, t)
        outside[t] = is_outside_bar(high, low, t)
        ioi[t] = is_ioi(high, low, t)
    return {"inside": inside, "outside": outside, "ioi": ioi}


# ---------------------------------------------------------------------------
# Per-symbol pipeline
# ---------------------------------------------------------------------------

def _bottom_opp_bars(
    stem: str,
    instrument_class: str,
    daily: pd.DataFrame,
    sixty: pd.DataFrame | None,
) -> tuple[set[int], tuple[int, int] | None]:
    """(bottom×opposing 信号的 daily bar 索引集, HTF 覆盖的 daily 索引区间)。

    返回的覆盖区间 (lo, hi)（含端点）是能判定 coincidence 的 daily bar 范围——
    区间外的 bar coincidence 未知（不能算 standalone，codex P2）。HTF 不可用
    返回 (set(), None)。

    Only the 60min higher-TF enrich is needed: bottom×opposing is defined purely
    by `higher_relation`, so we skip `enrich_with_lower_tf` (unused `lower_relation`,
    ~75% of enrich cost). Identical bottom×opposing set, far cheaper.
    """
    # enrich_with_higher_tf 需 >= MIN_HTF_BARS 根 60min bar 才能定 higher_relation
    # （_state_at_signal min_bars，codex P2）；覆盖窗起点取第 MIN_HTF_BARS 根，
    # 之前的 daily bar 仍处 HTF 暖机期、coincidence 未知。
    MIN_HTF_BARS = 60
    if sixty is None or len(sixty) < MIN_HTF_BARS:
        return set(), None
    sigs = detect_signals(daily, instrument_class=instrument_class)
    win_start = sixty["timestamp"].iloc[MIN_HTF_BARS - 1]
    win_end = sixty["timestamp"].iloc[-1]
    in_cov = (daily["timestamp"] >= win_start) & (daily["timestamp"] <= win_end)
    if not bool(in_cov.any()):
        return set(), None
    cov_idx = np.flatnonzero(in_cov.to_numpy())
    cov_range = (int(cov_idx[0]), int(cov_idx[-1]))
    in_window = [s for s in sigs
                 if win_start <= daily["timestamp"].iloc[s.candidate_bar_idx] <= win_end]
    enriched = enrich_with_higher_tf(in_window, daily, sixty, higher_tf_level_id="1h")
    out: set[int] = set()
    for sig in enriched:
        if sig.direction != "bottom":
            continue
        ctx = sig.multi_tf_context or {}
        if ctx.get("higher_relation") == "opposing":
            out.add(int(sig.candidate_bar_idx))
    return out, cov_range


def run_symbol_ioi(
    stem: str,
    instrument_class: str,
    *,
    quant_root: Path | None = None,
) -> tuple[list[dict], int]:
    """Returns (rows, n_bars). Each row = one pattern occurrence with forward
    outcomes. n_bars = total daily bars scanned (for frequency normalisation)."""
    def _load_tf(suffix: str, level: str) -> pd.DataFrame | None:
        df = _load_sym(stem, level, quant_root)
        if df is not None:
            return df
        p = DATA_DIR / f"{stem}_{suffix}.json"
        return load_bars(p) if p.exists() else None

    daily = _load_tf("daily", "D")
    if daily is None or daily.empty:
        return [], 0
    sixty = _load_tf("60", "60min")   # only the higher TF is needed (see _bottom_opp_bars)

    n = len(daily)
    atr_series = compute_atr(daily)
    close = daily["close"].to_numpy(dtype=float)
    flags = flag_patterns(daily)
    bottom_opp, cov_range = _bottom_opp_bars(stem, instrument_class, daily, sixty)

    rows: list[dict] = []
    for t in range(n):
        types = [p for p in PATTERN_TYPES if flags[p][t]]
        if not types:
            continue
        atr = float(atr_series.iloc[t])
        if not np.isfinite(atr) or atr <= 0:
            continue   # ATR 不可用（极早期 bar），forward 度量无法归一化

        # forward ATR-normalised returns (no lookahead; drop if window overruns)
        fwd: dict[str, float | None] = {}
        for k in FORWARD_KS:
            if t + k < n:
                fwd[f"fwd_atr_{k}"] = round((close[t + k] - close[t]) / atr, 6)
            else:
                fwd[f"fwd_atr_{k}"] = None

        # auxiliary directional measure: bottom-entry simulate_trade
        sim = simulate_trade(daily, t, "bottom", STOP_MULT, atr_series)
        if sim is not None:
            outcome, realized_r, _b1, _be = sim
        else:
            outcome, realized_r = None, None

        # HTF 覆盖内才能判定 coincidence；覆盖外标记 unknown（codex P2：
        # 不能把"未知"当 standalone，否则 standalone 组与零重叠结论被污染）
        htf_cov = cov_range is not None and cov_range[0] <= t <= cov_range[1]
        coincident = t in bottom_opp
        for ptype in types:
            rows.append({
                "symbol": stem,
                "date": daily["timestamp"].iloc[t].strftime("%Y-%m-%d"),
                "bar_idx": t,
                "pattern": ptype,
                "htf_coverage": bool(htf_cov),
                "coincident_bottom_opp": coincident,
                "atr": round(atr, 6),
                "sim_outcome": outcome,
                "sim_realized_r": (round(float(realized_r), 6)
                                   if realized_r is not None else None),
                **fwd,
            })
    return rows, n


# ---------------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------------

def _bootstrap_ci(vals: list[float], *, n_boot: int = BOOTSTRAP_N,
                  seed: int = BOOTSTRAP_SEED) -> tuple[float | None, float | None]:
    """95% bootstrap CI of the mean. Returns (lo, hi) or (None, None) if empty.

    Resamples in fixed-size batches so peak memory stays O(batch × n) regardless
    of sample size (a single (n_boot × n) matrix blows up for n in the thousands).
    """
    arr = np.asarray([v for v in vals if v is not None], dtype=float)
    if arr.size == 0:
        return None, None
    rng = np.random.default_rng(seed)
    n = arr.size
    batch = max(1, min(n_boot, 2_000_000 // max(n, 1)))  # cap ~2M cells per batch
    means = np.empty(n_boot, dtype=float)
    done = 0
    while done < n_boot:
        b = min(batch, n_boot - done)
        idx = rng.integers(0, n, size=(b, n))
        means[done:done + b] = arr[idx].mean(axis=1)
        done += b
    return round(float(np.percentile(means, 2.5)), 6), round(float(np.percentile(means, 97.5)), 6)


def _fwd_stats(rows: list[dict], key: str, *, with_ci: bool) -> dict:
    """Mean + hit-rate (>0) for a forward_atr_return horizon. Bootstrap CI is
    only computed when with_ci (reserved for the CI_K horizon per spec — running
    10k resamples on every horizon × block is needlessly expensive)."""
    vals = [r[key] for r in rows if r.get(key) is not None]
    if not vals:
        return {"n": 0, "ev": None, "hit_rate": None, "ci95": [None, None]}
    arr = np.asarray(vals, dtype=float)
    out = {
        "n": int(arr.size),
        "ev": round(float(arr.mean()), 6),
        "hit_rate": round(float((arr > 0).mean()), 4),
    }
    out["ci95"] = list(_bootstrap_ci(vals)) if with_ci else [None, None]
    return out


def _sim_stats(rows: list[dict]) -> dict:
    """simulate_trade bottom-entry EV/hit + bootstrap CI."""
    vals = [r["sim_realized_r"] for r in rows if r.get("sim_realized_r") is not None]
    if not vals:
        return {"n": 0, "ev": None, "tp1_rate": None, "full_stop_rate": None,
                "ci95": [None, None]}
    arr = np.asarray(vals, dtype=float)
    tp1 = sum(1 for r in rows if r.get("sim_outcome") in ("tp1_stop", "tp1_tp2", "tp1_max"))
    fs = sum(1 for r in rows if r.get("sim_outcome") == "full_stop")
    nn = len(vals)
    lo, hi = _bootstrap_ci(vals)
    return {
        "n": nn,
        "ev": round(float(arr.mean()), 6),
        "tp1_rate": round(tp1 / nn, 4),
        "full_stop_rate": round(fs / nn, 4),
        "ci95": [lo, hi],
    }


def _pattern_block(rows: list[dict]) -> dict:
    """All forward horizons + sim stats for a homogeneous row set. Bootstrap CI
    only on the CI_K horizon (+ sim) per the documented spec."""
    block = {f"fwd_atr_{k}": _fwd_stats(rows, f"fwd_atr_{k}", with_ci=(k == CI_K))
             for k in FORWARD_KS}
    block["sim_bottom"] = _sim_stats(rows)
    return block


def build_report(all_rows: list[dict], n_bars_by_pool: dict[str, int],
                 pools: list[str]) -> dict:
    def by_pattern(rs: list[dict]) -> dict:
        out = {}
        for p in PATTERN_TYPES:
            prows = [r for r in rs if r["pattern"] == p]
            out[p] = {"n": len(prows), **_pattern_block(prows)}
        return out

    # frequency: occurrences per 1000 bars (each pattern counted at the bars it
    # fires; a bar can be both inside-eligible and ioi, counted separately).
    pooled_bars = sum(n_bars_by_pool.values())

    def freq(rs: list[dict], bars: int) -> dict:
        return {
            p: round(1000.0 * sum(1 for r in rs if r["pattern"] == p) / bars, 4)
            if bars else None
            for p in PATTERN_TYPES
        }

    by_pool = {}
    for pool in pools:
        prs = [r for r in all_rows if r["_pool"] == pool]
        nb = n_bars_by_pool.get(pool, 0)
        by_pool[pool] = {
            "n_bars": nb,
            "n_occurrences": len(prs),
            "freq_per_1000_bars": freq(prs, nb),
            "by_pattern": by_pattern(prs),
        }

    # standalone vs coincident (bottom×opposing) split — 仅 HTF 覆盖内的 bar
    # （codex P2：覆盖外 coincidence 未知，单列 unknown，不混入 standalone）
    def coincidence_split(rs: list[dict]) -> dict:
        covered = [r for r in rs if r.get("htf_coverage")]
        unknown = [r for r in rs if not r.get("htf_coverage")]
        standalone = [r for r in covered if not r["coincident_bottom_opp"]]
        coincident = [r for r in covered if r["coincident_bottom_opp"]]
        return {
            "htf_covered_n": len(covered),
            "standalone": {"n": len(standalone), "by_pattern": by_pattern(standalone)},
            "coincident_bottom_opp": {"n": len(coincident),
                                      "by_pattern": by_pattern(coincident)},
            "unknown_no_htf_coverage": {"n": len(unknown)},
        }

    return {
        "params": {
            "patterns": list(PATTERN_TYPES),
            "pattern_defs": {
                "inside": "high[t]<=high[t-1] AND low[t]>=low[t-1]",
                "outside": "high[t]>=high[t-1] AND low[t]<=low[t-1]",
                "ioi": "inside(t-2) -> outside(t-1) -> inside(t), confirmed on t",
            },
            "no_lookahead": "patterns + forward windows use only bars <= detection bar; "
                            "forward windows dropped when t+k overruns the series",
            "forward_primary": "fwd_atr_k = (close[t+k]-close[t])/ATR[t], k in "
                               f"{list(FORWARD_KS)} (direction-free, ATR-relative)",
            "forward_auxiliary": "sim_bottom = simulate_trade(direction=bottom, entry=close[t], "
                                 f"ATR x{STOP_MULT} stop, 1R/2R, MAX_HOLD)",
            "atr_period": "backtest_rr_pool.ATR_PERIOD (14, EWMA)",
            "bootstrap": {"n": BOOTSTRAP_N, "seed": BOOTSTRAP_SEED, "ci": "95%",
                          "ci_on": [f"fwd_atr_{CI_K}", "sim_bottom"]},
            "coincidence": "bottom x higher_relation=opposing (validated population)",
            "pools": pools,
        },
        "pooled": {
            "n_bars": pooled_bars,
            "n_occurrences": len(all_rows),
            "freq_per_1000_bars": freq(all_rows, pooled_bars),
            "by_pattern": by_pattern(all_rows),
            "coincidence_split": coincidence_split(all_rows),
        },
        "by_pool": {
            pool: {**by_pool[pool],
                   "coincidence_split": coincidence_split(
                       [r for r in all_rows if r["_pool"] == pool])}
            for pool in pools
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pools", nargs="+", default=list(DEFAULT_POOLS),
                    choices=sorted(POOLS))
    ap.add_argument("--quant-root", type=Path,
                    default=bar_loader.DEFAULT_QUANT_ROOT,
                    help="quant-data Parquet root（默认 data/quant/）")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    all_rows: list[dict] = []
    n_bars_by_pool: dict[str, int] = {}
    for pool in args.pools:
        icls = POOL_INSTRUMENT_CLASS[pool]
        pool_bars = 0
        for stem in POOLS[pool]:
            rows, nbars = run_symbol_ioi(stem, icls, quant_root=args.quant_root)
            pool_bars += nbars
            for r in rows:
                r["_pool"] = pool
            all_rows.extend(rows)
            print(f"  scanned {stem}: bars={nbars} occ={len(rows)}", file=sys.stderr, flush=True)
        n_bars_by_pool[pool] = pool_bars

    print("aggregating + bootstrap...", file=sys.stderr, flush=True)
    report = build_report(all_rows, n_bars_by_pool, args.pools)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    pooled = report["pooled"]
    freq = pooled["freq_per_1000_bars"]
    print(f"wrote {args.out}  (bars={pooled['n_bars']} occ={pooled['n_occurrences']} "
          f"freq/1000: inside={freq['inside']} outside={freq['outside']} ioi={freq['ioi']})")


if __name__ == "__main__":
    main()
