"""End-to-end historical replay of the current score_today emission stack.

Replays the 8 active emit lanes over historical bars, simulates each
signal's forward outcome with the lane's structural stop, and records
the DIR verdict (without gating) so downstream analysis can answer
"what if DIR gated the production scorecard?".

The detectors are replay-safe (each scan uses up_to_idx semantics
internally), so we call each detector once per (symbol, lane) and
iterate over its full output rather than re-scanning per bar.

Outcomes (per backtest_rr_pool convention):
  full_stop  — stop hit before TP1                  → R = -1.0
  tp1_stop   — TP1 hit, then stopped at entry         → R =  0.0
  tp1_tp2    — TP1 + TP2 both hit                     → R = +1.5
  tp1_max    — TP1 hit, max-hold on remainder         → R = 0.5 + 0.5*(close-entry)/R
  max_hold   — neither TP nor stop hit by max_hold    → R = (close-entry)/R, capped ±3

Lanes covered:
  pa_us_60min  pa_us_dif_pos  pa_h2  pa_cn_bond
  pa_h2_climax vflush  context_a  bpull

Usage:
  uv run python scripts/backtest_full_stack.py
  uv run python scripts/backtest_full_stack.py --pool CN_METAL
  uv run python scripts/backtest_full_stack.py --since 2023-01-01
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from data import bar_loader
from engine.divergence.bpull_detector import BPullDetector
from engine.divergence.context_a_detector import ContextADetector
from engine.divergence.pa_detector import PABottomDetector
from engine.divergence.pa_direction_assessment import assess_direction
from engine.divergence.pa_structure import PAStructureDetector
from engine.divergence.vflush_detector import VFlushDetector
from engine.features.macd import macd as compute_macd
from engine.features.swing_context import compute_swing_context


def _default_review_dir() -> Path:
    derived = os.environ.get("DERIVED_ROOT")
    if derived:
        return Path(derived) / "paired-trading" / "src-data-review"
    return Path(__file__).resolve().parents[1] / "data" / "review"


# ---------------------------------------------------------------------------
# Pools (subset of score_today's POOLS, focused on PA-active universe)
# ---------------------------------------------------------------------------

US_SYMBOLS = ["SPY", "QQQ", "IWM", "DIA", "GLD", "GDX", "XLF", "XLK",
              "TLT", "NVDA", "XLB", "XLE", "XLRE", "XLU"]
CN_METAL = ["kq_m_shfe_cu", "kq_m_shfe_au", "kq_m_shfe_ag", "kq_m_ine_sc"]
CN_BOND = ["kq_m_cffex_tf", "kq_m_cffex_t", "kq_m_cffex_ts"]
CN_AGRI_POS = ["kq_m_dce_m",
               "kq_m_czce_ta", "kq_m_czce_ma", "kq_m_czce_sr"]
# kq_m_dce_p removed 2026-06-09 — palm oil 64% full_stop rate / -3.97R 5y;
# mirrors production score_today._CN_AGRI_POS_SYMBOLS exclusion.
# See doc/repro/agri_pos_dce_p_diagnosis_2026-06-09.md.
US_LONG_BOND_SUPPRESS = {"tlt", "tlh", "iei", "ief", "shy"}

POOL_TO_SYMBOLS = {
    "US": US_SYMBOLS,
    "CN_METAL": CN_METAL,
    "CN_BOND": CN_BOND,
    "CN_AGRI_POS": CN_AGRI_POS,
}
POOL_TO_CLASS = {
    "US": "us_equity",
    "CN_METAL": "cn_metal_futures",
    "CN_BOND": "cn_bond",
    "CN_AGRI_POS": "cn_futures",
}


# ---------------------------------------------------------------------------
# Trade simulation
# ---------------------------------------------------------------------------

@dataclass
class SimOutcome:
    outcome: str         # full_stop / tp1_stop / tp1_tp2 / tp1_max / max_hold
    realized_r: float
    bars_held: int


def _simulate_forward(
    bars: pd.DataFrame,
    entry_idx: int,
    entry_close: float,
    stop: float,
    max_hold: int,
) -> SimOutcome | None:
    """Bar-by-bar walk-forward outcome simulation.

    Within a bar: check stop direction BEFORE favourable direction
    (conservative fill assumption — mirrors backtest_rr_pool).
    """
    if stop is None or not np.isfinite(stop) or stop >= entry_close:
        return None
    risk = entry_close - stop
    if risk <= 0:
        return None
    tp1_level = entry_close + risk
    tp2_level = entry_close + 2 * risk
    hit_tp1 = False
    for off in range(1, max_hold + 1):
        i = entry_idx + off
        if i >= len(bars):
            break
        lo = float(bars["low"].iloc[i])
        hi = float(bars["high"].iloc[i])
        cl = float(bars["close"].iloc[i])
        if not hit_tp1:
            if lo <= stop:
                return SimOutcome("full_stop", -1.0, off)
            if hi >= tp1_level:
                hit_tp1 = True
                if hi >= tp2_level:
                    return SimOutcome("tp1_tp2", 1.5, off)
        else:
            if lo <= stop:
                return SimOutcome("tp1_stop", 0.0, off)
            if hi >= tp2_level:
                return SimOutcome("tp1_tp2", 1.5, off)
            if off == max_hold:
                tail = float(np.clip((cl - entry_close) / risk, -3, 3))
                return SimOutcome("tp1_max", 0.5 + 0.5 * tail, off)
    # Reached end of window without hitting TP1
    last_off = min(max_hold, len(bars) - entry_idx - 1)
    if last_off <= 0:
        return None
    last_close = float(bars["close"].iloc[entry_idx + last_off])
    r = float(np.clip((last_close - entry_close) / risk, -3, 3))
    return SimOutcome("max_hold", r, last_off)


# ---------------------------------------------------------------------------
# Lane scanners — each returns list of dicts (one per emitted signal)
# ---------------------------------------------------------------------------


def _structural_stop(
    bars: pd.DataFrame, bar_idx: int, entry_close: float,
) -> float | None:
    """PA structural stop (used by 6 of 8 lanes)."""
    struct = PAStructureDetector().detect(bars, up_to_idx=bar_idx)
    if struct.structural_stop is None:
        return None
    if struct.structural_stop >= entry_close:
        return None
    return float(struct.structural_stop)


def _lane_pa_h2_climax(sym: str, daily: pd.DataFrame, h_bars,
                       since: pd.Timestamp) -> list[dict]:
    if sym not in CN_AGRI_POS:
        return []
    det = PABottomDetector(min_h_legs=2, min_quality=0.3,
                          ema_threshold=0.0, min_gap=10,
                          require_climax=True, climax_threshold=0.4)
    out = []
    for sig in det.scan(daily, h_bars=h_bars):
        if sig.timestamp < since:
            continue
        if sig.higher_tf_relation != "opposing":
            continue
        entry = float(daily["close"].iloc[sig.bar_idx])
        stop = _structural_stop(daily, sig.bar_idx, entry)
        out.append({
            "lane": "pa_h2_climax", "symbol": sym,
            "timestamp": sig.timestamp, "bar_idx": int(sig.bar_idx),
            "entry": entry, "stop": stop,
            "policy_weight": 0.65,
        })
    return out


def _lane_pa_h2(sym: str, daily: pd.DataFrame, h_bars, since,
                instrument_class: str) -> list[dict]:
    if instrument_class != "cn_metal_futures":
        return []
    det = PABottomDetector(min_h_legs=2, min_quality=0.3,
                          ema_threshold=0.0, min_gap=10)
    out = []
    for sig in det.scan(daily, h_bars=h_bars):
        if sig.timestamp < since:
            continue
        w = PABottomDetector.policy_weight(sig, instrument_class, symbol=sym)
        if w == 0.0:
            continue
        entry = float(daily["close"].iloc[sig.bar_idx])
        stop = _structural_stop(daily, sig.bar_idx, entry)
        out.append({
            "lane": "pa_h2", "symbol": sym,
            "timestamp": sig.timestamp, "bar_idx": int(sig.bar_idx),
            "entry": entry, "stop": stop, "policy_weight": w,
        })
    return out


def _lane_pa_cn_bond(sym: str, daily: pd.DataFrame, h_bars, since,
                    instrument_class: str) -> list[dict]:
    if instrument_class != "cn_bond":
        return []
    det = PABottomDetector(min_h_legs=2, min_quality=0.3,
                          ema_threshold=0.0, min_gap=10)
    out = []
    for sig in det.scan(daily, h_bars=h_bars):
        if sig.timestamp < since:
            continue
        w = PABottomDetector.policy_weight(sig, instrument_class, symbol=sym)
        if w == 0.0:
            continue
        entry = float(daily["close"].iloc[sig.bar_idx])
        stop = _structural_stop(daily, sig.bar_idx, entry)
        out.append({
            "lane": "pa_cn_bond", "symbol": sym,
            "timestamp": sig.timestamp, "bar_idx": int(sig.bar_idx),
            "entry": entry, "stop": stop, "policy_weight": w,
        })
    return out


def _lane_pa_us_dif_pos(sym: str, daily: pd.DataFrame, h_bars, since,
                        instrument_class: str, macd_df) -> list[dict]:
    if instrument_class != "us_equity":
        return []
    if sym.lower() in US_LONG_BOND_SUPPRESS:
        return []
    det = PABottomDetector(min_h_legs=2, min_quality=0.3,
                          ema_threshold=0.0, min_gap=10)
    struct_det = PAStructureDetector()
    out = []
    for sig in det.scan(daily, h_bars=h_bars):
        if sig.timestamp < since:
            continue
        if sig.higher_tf_relation != "opposing":
            continue
        dif = float(macd_df["dif"].iloc[sig.bar_idx])
        if dif <= 0:
            continue
        struct = struct_det.detect(daily, up_to_idx=sig.bar_idx)
        if struct.phase in ("BEAR", "UNCLEAR"):
            continue
        if struct.structural_stop is None:
            continue
        entry = float(daily["close"].iloc[sig.bar_idx])
        if struct.structural_stop >= entry:
            continue
        weight = 0.65 if struct.phase == "BULL" else 0.30
        out.append({
            "lane": "pa_us_dif_pos", "symbol": sym,
            "timestamp": sig.timestamp, "bar_idx": int(sig.bar_idx),
            "entry": entry, "stop": float(struct.structural_stop),
            "policy_weight": weight,
        })
    return out


def _lane_pa_us_60min(sym: str, daily: pd.DataFrame, bars_60, since,
                      instrument_class: str) -> list[dict]:
    if instrument_class != "us_equity":
        return []
    if sym.lower() in US_LONG_BOND_SUPPRESS:
        return []
    if bars_60 is None or len(bars_60) < 100:
        return []
    swing_ctx = compute_swing_context(bars_60, swing_n=3)
    det = PABottomDetector(min_h_legs=2, min_quality=0.3,
                          ema_threshold=0.0, min_gap=35, h_lookback=20)
    out = []
    for sig in det.scan(bars_60, h_bars=daily, swing_context=swing_ctx):
        if sig.timestamp < since:
            continue
        if sig.higher_tf_relation != "opposing":
            continue
        trend = str(sig.features.get("trend_structure", ""))
        if trend != "uptrend":
            continue
        w = PABottomDetector.policy_weight(sig, instrument_class, symbol=sym)
        if w == 0.0:
            continue
        entry = float(bars_60["close"].iloc[sig.bar_idx])
        lo_win = bars_60["low"].iloc[max(0, sig.bar_idx - 10): sig.bar_idx + 1]
        floor = float(lo_win.min())
        stop = floor * 0.995 if floor < entry else None
        out.append({
            "lane": "pa_us_60min", "symbol": sym,
            "timestamp": sig.timestamp, "bar_idx": int(sig.bar_idx),
            "entry": entry, "stop": stop, "policy_weight": w,
            "_is_60min": True,
        })
    return out


def _lane_bpull(sym: str, daily: pd.DataFrame, h_bars, since,
                instrument_class: str) -> list[dict]:
    if instrument_class != "cn_metal_futures":
        return []
    det = BPullDetector()
    out = []
    for sig in det.scan(daily, h_bars):
        if sig.timestamp < since:
            continue
        w = BPullDetector.policy_weight(sig, instrument_class, symbol=sym)
        if w == 0.0:
            continue
        entry = float(daily["close"].iloc[sig.bar_idx])
        stop = _structural_stop(daily, sig.bar_idx, entry)
        out.append({
            "lane": "bpull", "symbol": sym,
            "timestamp": sig.timestamp, "bar_idx": int(sig.bar_idx),
            "entry": entry, "stop": stop, "policy_weight": w,
        })
    return out


def _lane_vflush(sym: str, daily: pd.DataFrame, h_bars, since,
                 instrument_class: str) -> list[dict]:
    if instrument_class != "cn_metal_futures":
        return []
    det = VFlushDetector()
    out = []
    for sig in det.scan(daily, h_bars):
        if sig.timestamp < since:
            continue
        w = VFlushDetector.policy_weight(sig, instrument_class, symbol=sym)
        if w == 0.0:
            continue
        entry = float(daily["close"].iloc[sig.bar_idx])
        signal_low = float(daily["low"].iloc[sig.bar_idx])
        stop = signal_low * 0.99 if signal_low < entry else None
        out.append({
            "lane": "vflush", "symbol": sym,
            "timestamp": sig.timestamp, "bar_idx": int(sig.bar_idx),
            "entry": entry, "stop": stop, "policy_weight": w,
        })
    return out


def _lane_context_a(sym: str, daily: pd.DataFrame, h_bars, since,
                    instrument_class: str) -> list[dict]:
    if instrument_class not in ("us_equity", "cn_metal_futures"):
        return []
    if sym.lower() in US_LONG_BOND_SUPPRESS:
        return []
    det = ContextADetector()
    out = []
    for sig in det.scan(daily, h_bars):
        if sig.timestamp < since:
            continue
        w = ContextADetector.policy_weight(sig, instrument_class, symbol=sym)
        if w == 0.0:
            continue
        entry = float(daily["close"].iloc[sig.bar_idx])
        stop = _structural_stop(daily, sig.bar_idx, entry)
        out.append({
            "lane": "context_a", "symbol": sym,
            "timestamp": sig.timestamp, "bar_idx": int(sig.bar_idx),
            "entry": entry, "stop": stop, "policy_weight": w,
        })
    return out


# ---------------------------------------------------------------------------
# DIR verdict (annotation only)
# ---------------------------------------------------------------------------


def _safe_assess(daily, h_bars, bar_idx, macd_df, *, signal_tf_bars=None,
                 signal_tf_label=None, signal_tf_bar_idx=None) -> tuple[str, float]:
    try:
        v = assess_direction(
            daily, h_bars, bar_idx, macd_df=macd_df,
            ambush_pattern="h2_bottom",
            signal_tf_bars=signal_tf_bars,
            signal_tf_label=signal_tf_label,
            signal_tf_bar_idx=signal_tf_bar_idx,
        )
        return v.direction, float(v.confidence)
    except Exception:
        return "skip", 0.0


# ---------------------------------------------------------------------------
# Per-symbol replay
# ---------------------------------------------------------------------------


def _load_bars(sym: str, level: str) -> pd.DataFrame | None:
    """Load via bar_loader.  60min for pa_us_60min, daily for the rest."""
    if level == "D":
        suffix = "_daily"
    elif level == "60min":
        suffix = "_60"
    elif level == "15min":
        suffix = "_15"
    else:
        suffix = f"_{level}"
    bars_dir = Path(__file__).resolve().parents[1] / "data" / "raw"
    return bar_loader.load_bars_quant_or_json(sym, suffix, bars_dir)


def replay_pool(pool: str, since_ts: pd.Timestamp,
                max_hold_daily: int = 20, max_hold_60min: int = 140) -> list[dict]:
    instrument_class = POOL_TO_CLASS[pool]
    rows: list[dict] = []
    for sym in POOL_TO_SYMBOLS[pool]:
        daily = _load_bars(sym, "D")
        if daily is None or len(daily) < 100:
            print(f"  {sym}: no daily")
            continue
        h_bars = _load_bars(sym, "60min")
        bars_60 = h_bars  # alias for pa_us_60min
        macd_df = compute_macd(daily["close"], hist_scale=1.0)

        # Collect raw signals from all relevant lanes
        raw: list[dict] = []
        raw.extend(_lane_pa_h2(sym, daily, h_bars, since_ts, instrument_class))
        raw.extend(_lane_pa_cn_bond(sym, daily, h_bars, since_ts, instrument_class))
        raw.extend(_lane_pa_us_dif_pos(sym, daily, h_bars, since_ts, instrument_class, macd_df))
        raw.extend(_lane_pa_us_60min(sym, daily, bars_60, since_ts, instrument_class))
        raw.extend(_lane_pa_h2_climax(sym, daily, h_bars, since_ts))
        raw.extend(_lane_bpull(sym, daily, h_bars, since_ts, instrument_class))
        raw.extend(_lane_vflush(sym, daily, h_bars, since_ts, instrument_class))
        raw.extend(_lane_context_a(sym, daily, h_bars, since_ts, instrument_class))

        for sig in raw:
            is_60m = sig.pop("_is_60min", False)
            sim_bars = bars_60 if is_60m else daily
            max_hold = max_hold_60min if is_60m else max_hold_daily
            outcome = _simulate_forward(
                sim_bars, sig["bar_idx"], sig["entry"], sig["stop"], max_hold,
            )
            if outcome is None:
                continue
            # DIR verdict (no gating, recorded for analysis)
            if is_60m:
                # Map 60min signal to daily bar_idx for DIR
                ts_np = pd.Timestamp(sig["timestamp"]).to_datetime64()
                daily_ts = pd.to_datetime(daily["timestamp"]).values
                mask = daily_ts <= ts_np
                daily_idx = int(mask.sum()) - 1 if mask.any() else 0
                verdict, conf = _safe_assess(
                    daily, bars_60, daily_idx, macd_df,
                    signal_tf_bars=bars_60, signal_tf_label="60min",
                    signal_tf_bar_idx=sig["bar_idx"],
                )
            else:
                verdict, conf = _safe_assess(daily, h_bars, sig["bar_idx"], macd_df)

            rows.append({
                "pool": pool,
                "instrument_class": instrument_class,
                "symbol": sig["symbol"],
                "lane": sig["lane"],
                "date": sig["timestamp"].date().isoformat(),
                "year": sig["timestamp"].year,
                "entry": sig["entry"],
                "stop": sig["stop"],
                "policy_weight": sig["policy_weight"],
                "outcome": outcome.outcome,
                "realized_r": outcome.realized_r,
                "bars_held": outcome.bars_held,
                "dir_verdict": verdict,
                "dir_confidence": conf,
                "is_60min": is_60m,
            })
        print(f"  {sym}: {len(rows)} cumulative rows after this symbol")

    return rows


def aggregate(df: pd.DataFrame) -> dict:
    """Top-line aggregates by lane / pool / year / verdict."""
    if df.empty:
        return {"n_trades": 0}
    by_lane = df.groupby("lane").agg(
        n=("realized_r", "size"),
        ev_R=("realized_r", "mean"),
        win_rate=("realized_r", lambda s: (s > 0).mean() * 100),
        median_R=("realized_r", "median"),
    ).round(3).to_dict("index")
    by_pool = df.groupby("pool").agg(
        n=("realized_r", "size"),
        ev_R=("realized_r", "mean"),
        win_rate=("realized_r", lambda s: (s > 0).mean() * 100),
    ).round(3).to_dict("index")
    by_year = df.groupby("year").agg(
        n=("realized_r", "size"),
        ev_R=("realized_r", "mean"),
    ).round(3).to_dict("index")
    by_verdict = df.groupby("dir_verdict").agg(
        n=("realized_r", "size"),
        ev_R=("realized_r", "mean"),
    ).round(3).to_dict("index")
    return {
        "n_trades": len(df),
        "total_R": round(df["realized_r"].sum(), 2),
        "ev_R": round(df["realized_r"].mean(), 3),
        "win_rate_pct": round((df["realized_r"] > 0).mean() * 100, 1),
        "max_drawdown_R": round(_max_drawdown(df["realized_r"]), 2),
        "by_lane": by_lane,
        "by_pool": by_pool,
        "by_year": by_year,
        "by_dir_verdict": by_verdict,
    }


def _max_drawdown(r_series: pd.Series) -> float:
    cum = r_series.sort_index().cumsum()
    peak = cum.cummax()
    return float((cum - peak).min())


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--pool", choices=list(POOL_TO_SYMBOLS) + ["ALL"],
                   default="ALL")
    p.add_argument("--since", default="2021-01-04",
                   help="ISO date — only emit signals on/after this")
    p.add_argument("--out-csv", type=Path,
                   default=_default_review_dir() / "full_stack_backtest.csv")
    p.add_argument("--out-json", type=Path, default=None,
                   help="Write backtest_output_v1 per-(lane,symbol) JSON for "
                        "validate_baselines.py --full")
    p.add_argument("--max-hold-daily", type=int, default=30,
                   help="Daily bar hold-cap for non-60min lanes (default 30; "
                        "raised from 20 per max_hold_experiment_2026-06-09.md: "
                        "+25%% EV / +38.72R across stack on 5.5y replay)")
    p.add_argument("--max-hold-60min", type=int, default=140,
                   help="60min bar hold-cap for pa_us_60min lane (default 140)")
    args = p.parse_args()

    since_ts = pd.Timestamp(args.since, tz="UTC")
    pools = list(POOL_TO_SYMBOLS) if args.pool == "ALL" else [args.pool]
    all_rows: list[dict] = []
    for pool in pools:
        print(f"\n=== {pool} ({POOL_TO_CLASS[pool]}) ===")
        rows = replay_pool(pool, since_ts,
                           max_hold_daily=args.max_hold_daily,
                           max_hold_60min=args.max_hold_60min)
        all_rows.extend(rows)
        print(f"{pool}: {len(rows)} trades")

    df = pd.DataFrame(all_rows)
    if not df.empty:
        args.out_csv.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(args.out_csv, index=False)
        print(f"\nWrote {len(df)} trades → {args.out_csv}")

    if args.out_json is not None and not df.empty:
        from scripts._baseline_output import write_baseline_output
        ls = df.groupby(["lane", "symbol"]).agg(
            n=("realized_r", "size"),
            ev_r=("realized_r", "mean"),
            win_pct=("realized_r", lambda s: (s > 0).mean() * 100),
        ).round(3)
        lanes: dict[str, dict] = {}
        for (lane, symbol), r in ls.iterrows():
            lanes.setdefault(lane, {})[symbol] = {
                "n": int(r["n"]), "ev_r": float(r["ev_r"]),
                "win_pct": round(float(r["win_pct"]), 1),
            }
        write_baseline_output(args.out_json, kind="full_stack", lanes=lanes,
                              data_hash=None)
        print(f"\nWrote backtest_output_v1 → {args.out_json}")

    agg = aggregate(df)
    print("\n=== HEADLINE ===")
    print(json.dumps({k: v for k, v in agg.items()
                      if k not in ("by_lane", "by_pool", "by_year", "by_dir_verdict")},
                     indent=2))
    print("\n=== BY LANE ===")
    for lane, stats in sorted(agg.get("by_lane", {}).items()):
        print(f"  {lane:14s} n={stats['n']:>4d} EV={stats['ev_R']:+.3f}R "
              f"win={stats['win_rate']:.1f}% median={stats['median_R']:+.3f}R")
    print("\n=== BY POOL ===")
    for pool, stats in sorted(agg.get("by_pool", {}).items()):
        print(f"  {pool:14s} n={stats['n']:>4d} EV={stats['ev_R']:+.3f}R "
              f"win={stats['win_rate']:.1f}%")
    print("\n=== BY DIR VERDICT (no gating, annotation only) ===")
    for v, stats in sorted(agg.get("by_dir_verdict", {}).items()):
        print(f"  {v:10s} n={stats['n']:>4d} EV={stats['ev_R']:+.3f}R")
    print("\n=== BY YEAR ===")
    for yr, stats in sorted(agg.get("by_year", {}).items()):
        print(f"  {yr} n={stats['n']:>4d} EV={stats['ev_R']:+.3f}R")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
