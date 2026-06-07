"""MCT event extractor and forward-return precision study.

Bar-scan approach (causal, no look-ahead): checks 3-TF aligned Mid-Cycle
Counter-trend (MCT) conditions at each daily bar and measures forward-return
precision at multiple horizons.

MCT UP bar: bearish MACD in active cycle, all three TFs bearish.
MCT DOWN bar: bullish MACD in active cycle, all three TFs bullish.

Signed forward return convention:
  UP direction → signed_ret = raw  (positive = price went up = continuation win)
  DOWN direction → signed_ret = -raw (positive = price went down = continuation win)

Pass criterion: CI_lo > 0  (95% bootstrap CI on mean signed return clears zero)

Lower-TF session-cutoff is instrument-class-aware:
  us_equity  → daily bar ts + 17h (covers 04:00→21:00 UTC, full NYSE session)
  cn_futures → daily bar ts + 16h (covers ~02:00→18:00 UTC, full CFFEX session)

Usage:
  uv run python scripts/detect_mct_events.py --pool US
  uv run python scripts/detect_mct_events.py --pool US -o data/review/mct_pool_us.csv
  uv run python scripts/detect_mct_events.py --pool CN --horizons 5 10 20
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from engine.features.macd import macd
from engine.features.streams import compute_feature_streams
from engine.units.snapshot import compute_unit_metadata

DEFAULT_BARS_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
DEFAULT_HORIZONS = [5, 10, 20]
N_BOOTSTRAP = 5000
RNG_SEED = 42

POOLS: dict[str, list[str]] = {
    "US": ["SPY", "QQQ", "IWM", "DIA", "GLD", "GDX", "XLF", "XLK", "TLT", "NVDA"],
    "CN": ["kq_m_cffex_if", "kq_m_cffex_ih", "kq_m_cffex_ic", "kq_m_cffex_im"],
}

POOL_INSTRUMENT_CLASS: dict[str, str] = {
    "US": "us_equity",
    "CN": "cn_index_futures",
}

# Hours to add to daily bar timestamp so that the lower-TF lookup covers
# the same trading session without leaking into the next day.
# us_equity: daily stamped 04:00 UTC; NYSE session ends ~20:00-21:00 UTC → +17h
# cn_futures: daily stamped 07:00 UTC (15:00 CST, session close); CFFEX day session
#             ends 15:00 CST → +16h covers through 23:00 UTC (07:00 CST next day),
#             safely past session close, before next-day open at 09:30 CST
SESSION_CUTOFF_HOURS: dict[str, int] = {
    "us_equity": 17,
    "cn_futures": 16,
    "cn_index_futures": 16,  # CFFEX stock index same session hours as cn_futures
    "czce": 16,
}


def load_bars(path: Path) -> pd.DataFrame:
    payload = json.loads(path.read_text())
    df = pd.DataFrame(payload["bars"])
    df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df.sort_values("timestamp").reset_index(drop=True)


def resample_to_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    """No-leak weekly bars (same logic as analyze_exhaustion_pool.py)."""
    if daily.empty:
        return daily.copy()
    df = daily.set_index("timestamp").sort_index()
    grouper = pd.Grouper(freq="W-FRI", label="right", closed="right")
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    if "volume" in df.columns:
        agg["volume"] = "sum"
    grouped = df.groupby(grouper)
    weekly = grouped.agg(agg).dropna(subset=["open"])
    if weekly.empty:
        return weekly.reset_index()
    last_ts = grouped.apply(lambda g: g.index.max() if len(g) else pd.NaT)
    src_tz = daily["timestamp"].dt.tz
    new_index = pd.to_datetime(last_ts.reindex(weekly.index).values, utc=src_tz is not None)
    if src_tz is not None and new_index.tz is None:
        new_index = new_index.tz_localize(src_tz)
    weekly.index = new_index
    weekly.index.name = "timestamp"
    return weekly.reset_index()


def _dif_sign(dif: float, tol: float = 1e-6) -> str:
    if dif > tol:
        return "pos"
    if dif < -tol:
        return "neg"
    return "zero"


def build_state_series(bars: pd.DataFrame) -> pd.DataFrame:
    """Compute per-bar MACD state vectors for a set of bars.

    Returns a DataFrame indexed 0..n-1 with columns:
      trend_side, cycle_state, dif_sign, dif, dea
    """
    macd_df = macd(bars["close"], hist_scale=1.0)
    streams = compute_feature_streams(
        bars["close"], macd_df["dif"], macd_df["dea"], macd_df["hist"],
    )
    units = compute_unit_metadata(
        macd_df["dif"], macd_df["dea"], macd_df["hist"], streams["dif_proximity_zero"],
    )
    state = pd.DataFrame(index=bars.index)
    state["timestamp"] = bars["timestamp"]
    state["dif"] = macd_df["dif"].values
    state["dea"] = macd_df["dea"].values
    state["trend_side"] = np.where(
        (macd_df["dif"].values > 0) & (macd_df["dea"].values > 0), "bullish",
        np.where(
            (macd_df["dif"].values < 0) & (macd_df["dea"].values < 0), "bearish",
            "transition",
        ),
    )
    state["dif_sign"] = macd_df["dif"].apply(_dif_sign).values
    state["cycle_state"] = units["cycle_state"].values
    return state


def foreign_trend_at(foreign_state: pd.DataFrame, head_ts: pd.Timestamp) -> str | None:
    """Lookup the trend_side of the foreign TF at the bar with timestamp <= head_ts.
    Returns None if no foreign bar covers the timestamp."""
    sub = foreign_state[foreign_state["timestamp"] <= head_ts]
    if sub.empty:
        return None
    return str(sub["trend_side"].iloc[-1])


def bootstrap_ci(x: np.ndarray) -> tuple[float, float]:
    if len(x) == 0:
        return float("nan"), float("nan")
    rng = np.random.default_rng(RNG_SEED)
    means = rng.choice(x, size=(N_BOOTSTRAP, len(x)), replace=True).mean(axis=1)
    lo, hi = np.quantile(means, [0.025, 0.975])
    return float(lo), float(hi)


def signed_forward_return(
    bars: pd.DataFrame, idx: int, horizon: int, swing_direction: str
) -> float | None:
    """Forward return signed by continuation direction.
    UP swing → positive = price went up = win.
    DOWN swing → positive = price went down = win.
    """
    if idx + horizon >= len(bars):
        return None
    entry = float(bars["close"].iloc[idx])
    target = float(bars["close"].iloc[idx + horizon])
    if entry == 0:
        return None
    raw = (target - entry) / entry
    return raw if swing_direction == "up" else -raw


def collect_mct_events(
    symbol: str,
    bars_dir: Path,
    *,
    horizons: list[int],
    instrument_class: str = "us_equity",
) -> list[dict]:
    daily_path = bars_dir / f"{symbol.lower()}_daily.json"
    if not daily_path.exists():
        print(f"  {symbol}: missing daily snapshot, skipped", file=sys.stderr)
        return []

    bars = load_bars(daily_path)
    daily_state = build_state_series(bars)

    # Higher TF: no-leak weekly synthesized from daily
    weekly_bars = resample_to_weekly(bars)
    weekly_state = build_state_series(weekly_bars) if not weekly_bars.empty else None

    # Lower TF: 60-minute (required for 3-TF alignment)
    hourly_path = bars_dir / f"{symbol.lower()}_60.json"
    if not hourly_path.exists():
        print(f"  {symbol}: missing 60min snapshot ({hourly_path.name}), skipped", file=sys.stderr)
        return []
    hourly_bars = load_bars(hourly_path)
    hourly_state = build_state_series(hourly_bars)

    # Bar-scan approach: check MCT conditions at each daily bar.
    # No swing dependency → fully causal, no look-ahead.
    # Direction: UP MCT = bar where price should move up next (bearish MACD, all TFs bearish).
    #            DOWN MCT = bar where price should move down next (bullish MACD, all TFs bullish).
    # To avoid event clustering (many consecutive bars with same conditions),
    # enforce a MIN_GAP between same-direction events.
    MIN_GAP = 5  # bars between same-direction MCT events
    last_up_idx = -MIN_GAP - 1
    last_down_idx = -MIN_GAP - 1

    rows: list[dict] = []
    for i in range(len(bars)):
        d = daily_state.iloc[i]
        entry_ts = bars["timestamp"].iloc[i]

        for direction, need_trend, need_dif_sign in [
            ("up", "bearish", "neg"),
            ("down", "bullish", "pos"),
        ]:
            if direction == "up" and i - last_up_idx < MIN_GAP:
                continue
            if direction == "down" and i - last_down_idx < MIN_GAP:
                continue

            if d["cycle_state"] != "in_cycle":
                continue
            if d["trend_side"] != need_trend:
                continue
            if d["dif_sign"] != need_dif_sign:
                continue

            session_hours = SESSION_CUTOFF_HOURS.get(instrument_class, 17)
            lower_cutoff = entry_ts + pd.Timedelta(hours=session_hours)
            h_trend = foreign_trend_at(weekly_state, entry_ts) if weekly_state is not None else None
            l_trend = foreign_trend_at(hourly_state, lower_cutoff) if hourly_state is not None else None

            if h_trend != need_trend or l_trend != need_trend:
                continue

            row: dict = {
                "symbol": symbol,
                "candidate_bar_idx": i,
                "timestamp": entry_ts.isoformat(),
                "direction": direction,
                "d_trend_side": str(d["trend_side"]),
                "d_cycle_state": str(d["cycle_state"]),
                "d_dif_sign": str(d["dif_sign"]),
                "h_trend_side": h_trend,
                "l_trend_side": l_trend,
            }
            for h in horizons:
                row[f"ret_h{h}"] = signed_forward_return(bars, i, h, direction)
            rows.append(row)

            if direction == "up":
                last_up_idx = i
            else:
                last_down_idx = i

    return rows


def summarize(vals: np.ndarray, label: str) -> dict:
    n = len(vals)
    if n == 0:
        return {"cell": label, "n": 0, "hit_pct": float("nan"),
                "mean_pct": float("nan"), "ci_lo": float("nan"), "ci_hi": float("nan")}
    hit = float(np.mean(vals > 0)) * 100.0
    mean = float(np.mean(vals)) * 100.0
    lo, hi = bootstrap_ci(vals)
    return {"cell": label, "n": n, "hit_pct": hit,
            "mean_pct": mean, "ci_lo": lo * 100.0, "ci_hi": hi * 100.0}


def print_table(cells: list[dict]) -> None:
    print(f"{'cell':<20} {'n':>5} {'hit%':>7} {'mean%':>8} {'CI95':>22}")
    print("-" * 68)
    for c in cells:
        if c["n"] == 0:
            print(f"{c['cell']:<20} {c['n']:>5d}  —")
            continue
        ci_str = f"[{c['ci_lo']:+.2f}, {c['ci_hi']:+.2f}]"
        pass_flag = " ✓" if c["ci_lo"] > 0 else ""
        print(f"{c['cell']:<20} {c['n']:>5d} {c['hit_pct']:>6.1f}% "
              f"{c['mean_pct']:>+7.2f}% {ci_str:>22}{pass_flag}")


def main() -> int:
    p = argparse.ArgumentParser(description="MCT 3-TF aligned event extractor + precision")
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--pool", choices=sorted(POOLS))
    grp.add_argument("--symbols", nargs="+")
    p.add_argument("--bars-dir", type=Path, default=DEFAULT_BARS_DIR)
    p.add_argument("--horizons", type=int, nargs="+", default=DEFAULT_HORIZONS)
    p.add_argument("--instrument-class", default=None, dest="instrument_class",
                   choices=list(SESSION_CUTOFF_HOURS))
    p.add_argument("-o", "--output", type=Path)
    args = p.parse_args()

    if any(h <= 0 for h in args.horizons):
        p.error("all horizons must be positive integers")

    symbols = POOLS[args.pool] if args.pool else args.symbols
    instrument_class = args.instrument_class or (
        POOL_INSTRUMENT_CLASS.get(args.pool, "us_equity") if args.pool else "us_equity"
    )
    print(f"Pool: {args.pool or 'custom'} ({len(symbols)} symbols, class={instrument_class})")
    print(f"Horizons: {args.horizons}  (bar-scan, MIN_GAP=5)")
    print()

    all_rows: list[dict] = []
    for sym in symbols:
        rows = collect_mct_events(
            sym, args.bars_dir,
            horizons=args.horizons,
            instrument_class=instrument_class,
        )
        print(f"  {sym}: {len(rows)} MCT events")
        all_rows.extend(rows)

    if not all_rows:
        print("\nNo MCT events found.")
        return 0

    df = pd.DataFrame(all_rows)
    n_up = int((df["direction"] == "up").sum())
    n_down = int((df["direction"] == "down").sum())
    print(f"\nTotal MCT events: {len(df)}  (up={n_up}  down={n_down})")
    print()

    # ── Precision by direction × horizon ───────────────────────────────────
    cells: list[dict] = []
    for h in args.horizons:
        col = f"ret_h{h}"
        for direction in ["up", "down", "all"]:
            sub = df if direction == "all" else df[df["direction"] == direction]
            vals = sub[col].dropna().to_numpy()
            cells.append(summarize(vals, f"h={h}  {direction:<5}"))

    print("Forward-return precision (signed: up→raw, down→-raw; CI_lo>0 passes):")
    print_table(cells)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(args.output, index=False)
        print(f"\nPer-event CSV → {args.output}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
