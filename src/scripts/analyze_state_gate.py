"""analyze_state_gate.py — 粗市场状态门控 EV 验证（PA 假设 t_aeb3cc75）。

Brooks 把市场切成 8 态；本脚本把它收敛成 4 个**可编程**粗态——
spike / tight_channel / normal_channel / range——纯由 OHLC 派生特征确定：
  - consec_dir：信号 bar 结尾的同向趋势 bar 连数（bull 或 bear 取主导方向）
  - overlap_ratio：近 N 根 bar 的平均重叠率（相邻 bar 的 [low,high] 区间重叠
    占两者并集的比例）。高重叠=区间/横盘；低重叠=趋势/急冲。
  - ema_dist_atr：|close - EMA20| / ATR（ATR 相对，**非固定价格 %**——债期整段
    波动 <2%，固定 % 阈值在债上必然全判 range）。
  - leg_overlap：近两条 swing leg 的价格区间重叠率（腿与腿高度重叠=区间震荡）。

收敛规则（详见 classify_market_state docstring），落到 4 态：
  spike          — 强同向连阳/连阴 + 大 EMA 偏离 + 低 bar 重叠（动量爆发）
  tight_channel  — 持续单向但 bar 重叠偏高、EMA 偏离温和（缓坡窄通道）
  normal_channel — 单向但结构松散（普通推进）
  range          — 高 bar 重叠 + 小 EMA 偏离 + 高腿重叠（横盘震荡）

**机械评估器：只输出统计，不打 PASS/FAIL，不解读裁决。**

复用已验证管道（不 fork backtest_rr_pool 逻辑）：
  detect_signals → enrich_with_higher_tf/lower_tf → simulate_trade（ATR×1.5 止损
  + 1R/2R 缩仓 + MAX_HOLD），EV = mean(realized_r)。
限定在 **bottom × higher_relation=opposing** 信号群（已验证强信号 lane）。
对每个信号 bar 算粗态，再按态分组 realized_r 的 EV + 胜率，pooled 与
by-pool（CN_BOND / CN_METAL / US_EQUITY）分开报（regime not portable：
不假设一池标定的门控可移植到另一池）。

无前视：信号 bar 的态只用 <= 信号 bar 的信息算（trend 连数、重叠、EMA、ATR、
swing leg 全部排除未来 bar；窗口端点含/不含已逐项校验）。

best-vs-rest 态 EV 差给 bootstrap（10000，seed=42）CI。

Usage:
  uv run python scripts/analyze_state_gate.py --pools CN_BOND CN_METAL US_EQUITY \
      --out data/review/state_gate_bottom_opp.json
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
    DATA_DIR,
    POOL_INSTRUMENT_CLASS,
    POOLS,
    _load_sym,
    compute_atr,
    detect_signals,
    load_bars,
    simulate_trade,
)

# --- 分类器参数（写死，输出到 JSON params）-------------------------------
EMA_PERIOD = 20        # EMA 距离基准周期
TREND_WINDOW = 6       # bar 重叠率统计窗口（含信号 bar，往前 TREND_WINDOW 根）
SWING_N = 3            # detect_swing_points 两侧确认根数（与 backtest 一致）
STOP_MULT = 1.5        # ATR 止损倍数（与 validated 口径一致）
# apply_policy 支持的 instrument_class（cn_bond 无规则 → 放行，见 run_symbol）
_POLICY_CLASSES = {"us_equity", "cn_futures", "czce",
                   "cn_index_futures", "cn_metal_futures"}

# 收敛阈值（ATR 相对 / 比例，无固定价格 %）
SPIKE_CONSEC = 3       # spike 至少同向连数
SPIKE_EMA_ATR = 1.5    # spike 至少 EMA 偏离（ATR 单位）
SPIKE_OVERLAP = 0.35   # spike 至多 bar 重叠率（低=急冲）
CHANNEL_CONSEC = 2     # channel 至少同向连数
TIGHT_OVERLAP = 0.55   # tight_channel 至少 bar 重叠率（窄=高重叠缓坡）
RANGE_OVERLAP = 0.55   # range 至少 bar 重叠率
RANGE_EMA_ATR = 1.0    # range 至多 EMA 偏离（贴近 EMA）
RANGE_LEG_OVERLAP = 0.30  # range 至少近两腿重叠率（腿叠=横盘）

BOOTSTRAP_N = 10000
BOOTSTRAP_SEED = 42
DEFAULT_POOLS = ("CN_BOND", "CN_METAL", "US_EQUITY")
STATES = ("spike", "tight_channel", "normal_channel", "range")


# ---------------------------------------------------------------------------
# Pure feature helpers (no lookahead — all operate on bars[:idx+1])
# ---------------------------------------------------------------------------

def _pair_overlap(lo_a: float, hi_a: float, lo_b: float, hi_b: float) -> float:
    """两 bar [low,high] 区间重叠率 = overlap / union（0..1）。"""
    inter = min(hi_a, hi_b) - max(lo_a, lo_b)
    if inter <= 0:
        return 0.0
    union = max(hi_a, hi_b) - min(lo_a, lo_b)
    if union <= 0:
        return 1.0
    return float(inter / union)


def bar_overlap_ratio(
    lows: np.ndarray, highs: np.ndarray, idx: int, window: int,
) -> float:
    """近 window 根 bar（含信号 bar idx）相邻对的平均重叠率（无前视）。

    严格用 [idx-window+1, idx] 这 window 根 bar 的 window-1 个相邻对；首对
    (idx-window+1, idx-window+2)，不触碰 idx-window 及更早、也不碰 idx 之后
    （codex P2：原 start=idx-window+1 会让首对回探到 idx-window，多算 1 根）。
    """
    start = max(1, idx - window + 2)
    pairs = []
    for j in range(start, idx + 1):
        pairs.append(_pair_overlap(lows[j - 1], highs[j - 1], lows[j], highs[j]))
    if not pairs:
        return 0.0
    return float(np.mean(pairs))


def consec_dir_count(
    opens: np.ndarray, closes: np.ndarray, idx: int,
) -> tuple[int, str]:
    """信号 bar 结尾的同向趋势 bar 连数 + 主导方向（无前视）。

    从 idx 往回数：先看信号 bar 自身方向（bull: close>open / bear: close<open），
    再沿同方向连续累计。doji（close==open）按 0 连数处理。
    """
    if closes[idx] > opens[idx]:
        direction = "bull"
    elif closes[idx] < opens[idx]:
        direction = "bear"
    else:
        return 0, "none"
    count = 0
    j = idx
    while j >= 0:
        if direction == "bull" and closes[j] > opens[j]:
            count += 1
        elif direction == "bear" and closes[j] < opens[j]:
            count += 1
        else:
            break
        j -= 1
    return count, direction


def leg_overlap_ratio(
    bars: pd.DataFrame, sl_idx: np.ndarray, sh_idx: np.ndarray, idx: int,
    *, swing_n: int,
) -> float:
    """近两条已确认 swing leg 的价格区间重叠率（无前视）。

    取 idx 之前**已确认**（swing_idx + swing_n <= idx）的最后两个 swing 锚点
    （任意高低混合），各自 [min(low,high区间)] 用 swing bar 的 [low,high] 近似
    一条腿的价位带，算两带重叠率。腿高度重叠=横盘震荡。少于 2 个确认锚 → 0。
    """
    confirmed = np.concatenate([
        sl_idx[sl_idx + swing_n <= idx],
        sh_idx[sh_idx + swing_n <= idx],
    ])
    confirmed = np.unique(confirmed[confirmed < idx])
    if confirmed.size < 2:
        return 0.0
    a, b = int(confirmed[-2]), int(confirmed[-1])
    lows = bars["low"].values
    highs = bars["high"].values
    return _pair_overlap(lows[a], highs[a], lows[b], highs[b])


# ---------------------------------------------------------------------------
# Coarse market-state classifier (pure, no lookahead)
# ---------------------------------------------------------------------------

def classify_market_state(
    bars: pd.DataFrame,
    idx: int,
    sl_idx: np.ndarray,
    sh_idx: np.ndarray,
    atr_series: pd.Series,
    ema_series: pd.Series,
    *,
    ema_period: int = EMA_PERIOD,
    window: int = TREND_WINDOW,
    swing_n: int = SWING_N,
) -> dict | None:
    """信号 bar idx 的粗市场状态（无前视）。返回 features+state 或 None（ATR 无效）。

    收敛规则（按优先级，先到先得）：
      1. spike          — consec_dir >= SPIKE_CONSEC 且 ema_dist_atr >= SPIKE_EMA_ATR
                          且 overlap_ratio <= SPIKE_OVERLAP（强动量爆发：连阳/阴、
                          远离 EMA、bar 几乎不重叠）。
      2. range          — overlap_ratio >= RANGE_OVERLAP 且 ema_dist_atr <= RANGE_EMA_ATR
                          且 leg_overlap >= RANGE_LEG_OVERLAP（高重叠、贴 EMA、腿叠）。
      3. tight_channel  — consec_dir >= CHANNEL_CONSEC 且 overlap_ratio >= TIGHT_OVERLAP
                          （单向但 bar 重叠高=缓坡窄通道）。
      4. normal_channel — 其余（单向推进但结构松散 / 不满足上面任何一类）。

    所有特征仅用 <= idx 的 bar；EMA/ATR 取 idx 当根值（series 本身是因果累计）。
    """
    atr = float(atr_series.iloc[idx])
    if not np.isfinite(atr) or atr <= 0:
        return None

    lows = bars["low"].values
    highs = bars["high"].values
    opens = bars["open"].values
    closes = bars["close"].values

    overlap = bar_overlap_ratio(lows, highs, idx, window)
    consec, direction = consec_dir_count(opens, closes, idx)
    ema_val = float(ema_series.iloc[idx])
    ema_dist_atr = abs(float(closes[idx]) - ema_val) / atr
    leg_ov = leg_overlap_ratio(bars, sl_idx, sh_idx, idx, swing_n=swing_n)

    if (consec >= SPIKE_CONSEC and ema_dist_atr >= SPIKE_EMA_ATR
            and overlap <= SPIKE_OVERLAP):
        state = "spike"
    elif (overlap >= RANGE_OVERLAP and ema_dist_atr <= RANGE_EMA_ATR
          and leg_ov >= RANGE_LEG_OVERLAP):
        state = "range"
    elif consec >= CHANNEL_CONSEC and overlap >= TIGHT_OVERLAP:
        state = "tight_channel"
    else:
        state = "normal_channel"

    return {
        "state": state,
        "consec_dir": int(consec),
        "consec_direction": direction,
        "overlap_ratio": round(overlap, 4),
        "ema_dist_atr": round(ema_dist_atr, 4),
        "leg_overlap": round(leg_ov, 4),
    }


# ---------------------------------------------------------------------------
# Per-symbol pipeline (mirrors backtest_rr_pool.run_symbol; adds state)
# ---------------------------------------------------------------------------

def run_symbol_state_gate(
    stem: str,
    instrument_class: str,
    *,
    apply_policy_gate: bool,
    quant_root: Path | None = None,
) -> list[dict]:
    """单品种 bottom×opposing 事件 + 粗市场状态 + realized_r。"""
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
    ema_series = daily["close"].ewm(span=EMA_PERIOD, adjust=False).mean()
    sh_idx, sl_idx = detect_swing_points(daily, n=SWING_N)

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
        # cn_bond 无 apply_policy 规则 → 放行（codex P2：否则 --apply-policy
        # 在 CN_BOND 上抛 ValueError；production 同样不在此层门控 cn_bond）
        if (apply_policy_gate and instrument_class in _POLICY_CLASSES
                and apply_policy(sig, instrument_class=instrument_class).weight == 0.0):
            continue

        idx = sig.candidate_bar_idx
        cls = classify_market_state(daily, idx, sl_idx, sh_idx,
                                    atr_series, ema_series)
        if cls is None:
            continue   # ATR 不可用（极早期 bar）

        sim = simulate_trade(daily, idx, "bottom", STOP_MULT, atr_series)
        if sim is None:
            continue
        outcome, realized_r, _bars_tp1, _bars_exit = sim
        rows.append({
            "symbol": stem,
            "date": sig.timestamp.strftime("%Y-%m-%d"),
            "state": cls["state"],
            "consec_dir": cls["consec_dir"],
            "overlap_ratio": cls["overlap_ratio"],
            "ema_dist_atr": cls["ema_dist_atr"],
            "leg_overlap": cls["leg_overlap"],
            "confidence": round(float(sig.confidence), 4),
            "outcome": outcome,
            "realized_r": round(float(realized_r), 6),
        })
    return rows


# ---------------------------------------------------------------------------
# Stats + bootstrap
# ---------------------------------------------------------------------------

def _group_stats(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0, "ev": None, "win_rate": None, "full_stop_rate": None}
    rs = [r["realized_r"] for r in rows]
    n = len(rs)
    wins = sum(1 for r in rows if r["realized_r"] > 0)
    fs = sum(1 for r in rows if r["outcome"] == "full_stop")
    return {
        "n": n,
        "ev": round(float(np.mean(rs)), 6),
        "win_rate": round(wins / n, 4),
        "full_stop_rate": round(fs / n, 4),
    }


def _by_state(rows: list[dict]) -> dict:
    return {st: _group_stats([r for r in rows if r["state"] == st]) for st in STATES}


def bootstrap_best_vs_rest(
    rows: list[dict], *, n_boot: int = BOOTSTRAP_N, seed: int = BOOTSTRAP_SEED,
) -> dict:
    """best-vs-rest 态 EV 差的 bootstrap CI。

    best = pooled 中样本 EV 最高且 n>=5 的态；rest = 其余所有事件。重抽样在
    best 组与 rest 组各自有放回抽样，计 EV(best)-EV(rest) 的分布。
    """
    by_state = _by_state(rows)
    eligible = {st: s for st, s in by_state.items()
                if s["n"] >= 5 and s["ev"] is not None}
    if len(eligible) < 1 or len(rows) == 0:
        return {"applicable": False,
                "reason": "no state with n>=5"}
    best_state = max(eligible, key=lambda st: eligible[st]["ev"])
    best_r = np.array([r["realized_r"] for r in rows if r["state"] == best_state])
    rest_r = np.array([r["realized_r"] for r in rows if r["state"] != best_state])
    if best_r.size < 5 or rest_r.size < 5:
        return {"applicable": False,
                "reason": "best or rest group has n<5",
                "best_state": best_state}

    rng = np.random.default_rng(seed)
    gaps = np.empty(n_boot, dtype=float)
    for i in range(n_boot):
        bb = rng.choice(best_r, size=best_r.size, replace=True)
        rr = rng.choice(rest_r, size=rest_r.size, replace=True)
        gaps[i] = bb.mean() - rr.mean()
    point = float(best_r.mean() - rest_r.mean())
    lo, hi = np.percentile(gaps, [2.5, 97.5])
    return {
        "applicable": True,
        "best_state": best_state,
        "best_n": int(best_r.size),
        "best_ev": round(float(best_r.mean()), 6),
        "rest_n": int(rest_r.size),
        "rest_ev": round(float(rest_r.mean()), 6),
        "gap_point": round(point, 6),
        "gap_ci95": [round(float(lo), 6), round(float(hi), 6)],
        "gap_ci_excludes_zero": bool(lo > 0 or hi < 0),
        "n_boot": n_boot,
        "seed": seed,
    }


def build_report(rows: list[dict], *, apply_policy_gate: bool,
                 pools: list[str]) -> dict:
    by_pool = {}
    for pool in pools:
        prs = [r for r in rows if r["_pool"] == pool]
        by_pool[pool] = {
            "n": len(prs),
            "by_state": _by_state(prs),
            "bootstrap_best_vs_rest": bootstrap_best_vs_rest(prs),
        }

    return {
        "params": {
            "signal_population": "bottom × higher_relation=opposing",
            "policy_gate_applied": apply_policy_gate,
            "states": list(STATES),
            "ema_period": EMA_PERIOD,
            "trend_window": TREND_WINDOW,
            "swing_n": SWING_N,
            "stop_mult": STOP_MULT,
            "max_hold": "backtest_rr_pool.MAX_HOLD",
            "thresholds": {
                "spike_consec": SPIKE_CONSEC, "spike_ema_atr": SPIKE_EMA_ATR,
                "spike_overlap_max": SPIKE_OVERLAP,
                "channel_consec": CHANNEL_CONSEC, "tight_overlap_min": TIGHT_OVERLAP,
                "range_overlap_min": RANGE_OVERLAP, "range_ema_atr_max": RANGE_EMA_ATR,
                "range_leg_overlap_min": RANGE_LEG_OVERLAP,
            },
            "ev": "mean(realized_r); win_rate = frac(realized_r>0); "
                  "realized_r per backtest_rr_pool outcomes",
            "lookahead": "state uses only bars<=signal_idx (trend/overlap/EMA/ATR/legs)",
            "pools": pools,
        },
        "n_events": len(rows),
        "pooled": {
            "by_state": _by_state(rows),
            "bootstrap_best_vs_rest": bootstrap_best_vs_rest(rows),
        },
        "by_pool": by_pool,
        "state_histogram": {
            st: sum(1 for r in rows if r["state"] == st) for st in STATES
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
            rows = run_symbol_state_gate(
                stem, icls, apply_policy_gate=args.apply_policy,
                quant_root=args.quant_root)
            for r in rows:
                r["_pool"] = pool
            all_rows.extend(rows)

    report = build_report(all_rows, apply_policy_gate=args.apply_policy,
                          pools=args.pools)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    hist = report["state_histogram"]
    bs = report["pooled"]["bootstrap_best_vs_rest"]
    print(f"wrote {args.out}  (n={report['n_events']}  hist={hist})")
    if bs.get("applicable"):
        print(f"  best={bs['best_state']} ev={bs['best_ev']} vs rest ev={bs['rest_ev']} "
              f"gap={bs['gap_point']} ci95={bs['gap_ci95']}")


if __name__ == "__main__":
    main()
