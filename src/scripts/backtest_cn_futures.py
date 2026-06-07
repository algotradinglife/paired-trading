"""CN futures aggregate backtest — single-TF divergence detection across 19 symbols.

Mirrors scripts/backtest_signals.py but:
  - Pools 19 主力连续合约 (continuous main contract) daily snapshots.
  - Re-uses the engine in-memory (no stdout parsing).
  - Emits a long-format CSV (per-symbol × per-direction × per-horizon) to
    data/review/cn_futures_signals_aggregate.csv
  - Prints all aggregate tables required by the CN-futures task brief.

Caveats:
  - 主力连续 series splice contracts → some price gaps at rollover may inflate
    a small fraction of forward returns. We do NOT filter them; we flag the
    worst |signed_return| outliers per horizon.
  - No 60min / weekly bars → multi_tf_context is None → fusion rules
    F1/F2/F3/F4 cannot fire. F8 (bottom + weakness) and direction_gate baseline
    DO apply.

Usage:
  uv run python scripts/backtest_cn_futures.py [min_conf]
  default min_conf = 0.30
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from engine.divergence.detector import detect_all_divergences
from engine.divergence.signal import DivergenceSignal
from engine.features.macd import macd
from engine.features.streams import compute_feature_streams
from engine.units.snapshot import compute_unit_metadata

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "raw"
REVIEW_DIR = ROOT / "data" / "review"
REVIEW_DIR.mkdir(parents=True, exist_ok=True)

SYMBOLS = [
    # Index futures (CFFEX)
    "if0", "ih0", "ic0", "im0",
    # Commodity futures
    "cu0", "m0", "au0", "ag0", "rb0", "i0", "j0", "jm0",
    "p0", "y0", "ta0", "ma0", "cf0", "sr0", "sc0",
]

INDEX_FUTURES = {"if0", "ih0", "ic0", "im0"}

FORWARD_WINDOWS = [5, 10, 20]
CSV_OUT = REVIEW_DIR / "cn_futures_signals_aggregate.csv"

CONF_BANDS = [
    ("watching", 0.30, 0.50),
    ("forming", 0.50, 0.65),
    ("candidate", 0.65, 0.80),
    ("confirmed", 0.80, 1.01),
]


@dataclass
class EvalRow:
    symbol: str
    signal: DivergenceSignal
    entry_idx: int
    entry_close: float
    fwd_returns: dict[int, float]
    signed_returns: dict[int, float]
    hits: dict[int, bool]
    mfes: dict[int, float]
    maes: dict[int, float]


def conf_band(c: float) -> str:
    for name, lo, hi in CONF_BANDS:
        if lo <= c < hi:
            return name
    return "dormant"


def load_bars(path: Path) -> pd.DataFrame:
    payload = json.loads(path.read_text())
    df = pd.DataFrame(payload["bars"])
    df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df.sort_values("timestamp").reset_index(drop=True)


def detect_for_symbol(symbol: str, *, min_conf: float) -> tuple[list[EvalRow], int, str]:
    path = DATA_DIR / f"{symbol}_daily.json"
    if not path.exists():
        return [], 0, ""
    bars = load_bars(path)
    n = len(bars)
    rng = (bars["timestamp"].iloc[0].strftime("%Y-%m-%d")
           + " -> " + bars["timestamp"].iloc[-1].strftime("%Y-%m-%d"))

    macd_df = macd(bars["close"], hist_scale=1.0)
    streams = compute_feature_streams(
        bars["close"], macd_df["dif"], macd_df["dea"], macd_df["hist"]
    )
    units = compute_unit_metadata(
        macd_df["dif"], macd_df["dea"], macd_df["hist"], streams["dif_proximity_zero"]
    )
    sigs = detect_all_divergences(
        units_df=units, ohlc=bars, dif=macd_df["dif"], hist=macd_df["hist"],
        level_id=symbol,
    )
    sigs = [s for s in sigs if s.confidence >= min_conf]

    rows: list[EvalRow] = []
    max_h = max(FORWARD_WINDOWS)
    for s in sigs:
        idx = s.candidate_bar_idx
        if idx + max_h >= len(bars):
            continue
        entry_close = float(bars["close"].iloc[idx])
        fwd, signed, hits, mfes, maes = {}, {}, {}, {}, {}
        for h in FORWARD_WINDOWS:
            tgt = float(bars["close"].iloc[idx + h])
            ret = (tgt - entry_close) / entry_close
            sgn = -ret if s.direction == "top" else ret
            window = bars.iloc[idx + 1 : idx + 1 + h]
            max_high = float(window["high"].max())
            min_low = float(window["low"].min())
            up_ret = (max_high - entry_close) / entry_close
            down_ret = (entry_close - min_low) / entry_close
            if s.direction == "top":
                mfe, mae = down_ret, up_ret
            else:
                mfe, mae = up_ret, down_ret
            fwd[h] = ret
            signed[h] = sgn
            hits[h] = sgn > 0
            mfes[h] = mfe
            maes[h] = mae
        rows.append(EvalRow(
            symbol=symbol, signal=s, entry_idx=idx, entry_close=entry_close,
            fwd_returns=fwd, signed_returns=signed, hits=hits, mfes=mfes, maes=maes,
        ))
    return rows, n, rng


def long_format(rows: list[EvalRow]) -> pd.DataFrame:
    records = []
    for r in rows:
        for h in FORWARD_WINDOWS:
            records.append({
                "symbol": r.symbol,
                "is_index_future": r.symbol in INDEX_FUTURES,
                "date": r.signal.timestamp.strftime("%Y-%m-%d"),
                "level": r.signal.level,
                "subtype": r.signal.subtype,
                "direction": r.signal.direction,
                "confidence": round(r.signal.confidence, 4),
                "conf_band": conf_band(r.signal.confidence),
                "horizon": h,
                "entry_close": r.entry_close,
                "fwd_return": r.fwd_returns[h],
                "signed_return": r.signed_returns[h],
                "hit": r.hits[h],
                "mfe": r.mfes[h],
                "mae": r.maes[h],
            })
    return pd.DataFrame(records)


def summary_by(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    g = df.groupby(cols, dropna=False)
    out = pd.DataFrame({
        "n": g.size(),
        "hit_rate": g["hit"].mean(),
        "avg_signed_ret_pct": g["signed_return"].mean() * 100,
        "median_signed_ret_pct": g["signed_return"].median() * 100,
        "avg_mfe_pct": g["mfe"].mean() * 100,
        "avg_mae_pct": g["mae"].mean() * 100,
    }).reset_index()
    out["mfe_mae_ratio"] = out["avg_mfe_pct"] / out["avg_mae_pct"]
    return out


def fmt_table(df: pd.DataFrame, title: str) -> str:
    if df.empty:
        return f"\n=== {title} ===\n  (no data)\n"
    show = df.copy()
    if "hit_rate" in show.columns:
        show["hit_rate"] = (show["hit_rate"] * 100).round(1).astype(str) + "%"
    for col in ["avg_signed_ret_pct", "median_signed_ret_pct", "avg_mfe_pct", "avg_mae_pct"]:
        if col in show.columns:
            show[col] = show[col].round(2).astype(str) + "%"
    if "mfe_mae_ratio" in show.columns:
        show["mfe_mae_ratio"] = show["mfe_mae_ratio"].round(2)
    show["n"] = show["n"].astype(int)
    return f"\n=== {title} ===\n" + show.to_string(index=False) + "\n"


def main(argv: list[str]) -> int:
    # Pre-extract --quant-data-root (no-op: CN kq_m_ symbols always use JSON)
    clean: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--quant-data-root" and i + 1 < len(argv):
            i += 2
        elif argv[i].startswith("--quant-data-root="):
            i += 1
        else:
            clean.append(argv[i])
            i += 1
    argv = clean
    min_conf = float(argv[0]) if argv else 0.30
    print(f"CN futures backtest — min_conf={min_conf:.2f}  horizons={FORWARD_WINDOWS}\n")

    all_rows: list[EvalRow] = []
    per_sym_stats = []
    for sym in SYMBOLS:
        rows, n_bars, rng = detect_for_symbol(sym, min_conf=min_conf)
        print(f"  {sym:5s}: n_bars={n_bars:5d}  signals={len(rows):4d}  range={rng}")
        per_sym_stats.append({"symbol": sym, "n_bars": n_bars, "n_signals": len(rows)})
        all_rows.extend(rows)

    if not all_rows:
        print("\nNo evaluable signals.")
        return 0

    df = long_format(all_rows)
    df.to_csv(CSV_OUT, index=False)
    print(f"\nLong-format CSV exported → {CSV_OUT}")
    print(f"Rows: {len(df)}  (signals={len(all_rows)} × horizons={len(FORWARD_WINDOWS)})")

    # ---- Per-symbol × horizon=20 summary ----
    df20 = df[df["horizon"] == 20]
    sym_dir = summary_by(df20, ["symbol", "direction"])
    print(fmt_table(sym_dir, "Per symbol × direction (h=20)"))

    sym_all = summary_by(df20, ["symbol"])
    print(fmt_table(sym_all.sort_values("avg_signed_ret_pct", ascending=False),
                    "Per symbol (h=20) — sorted by avg signed return"))

    # ---- Direction baseline ----
    print(fmt_table(summary_by(df20, ["direction"]),
                    "Direction baseline (h=20)"))

    # ---- Subtype pooled ----
    print(fmt_table(summary_by(df20, ["subtype"]),
                    "Subtype pooled (h=20)"))

    # ---- Conf band pooled ----
    print(fmt_table(summary_by(df20, ["conf_band"]),
                    "Confidence band pooled (h=20)"))

    # ---- Direction × subtype ----
    print(fmt_table(summary_by(df20, ["direction", "subtype"]),
                    "Direction × subtype (h=20)"))

    # ---- F8 isolation (bottom + weakness) ----
    f8 = df20[(df20["direction"] == "bottom") & (df20["subtype"] == "weakness")]
    if not f8.empty:
        print(fmt_table(summary_by(f8, ["conf_band"]),
                        "F8 isolation: bottom+weakness × conf_band (h=20)"))

    # ---- All horizons direction summary ----
    print(fmt_table(summary_by(df, ["direction", "horizon"]),
                    "Direction × horizon (all)"))

    # ---- Index vs commodity futures ----
    df20_ix = df20[df20["is_index_future"]]
    df20_cm = df20[~df20["is_index_future"]]
    print(fmt_table(summary_by(df20_ix, ["direction"]),
                    "Index futures only — direction (h=20)"))
    print(fmt_table(summary_by(df20_cm, ["direction"]),
                    "Commodity futures only — direction (h=20)"))

    # ---- Outlier flag: |signed_return| > 25% at h=20 ----
    extreme = df20[df20["signed_return"].abs() > 0.25].copy()
    if not extreme.empty:
        extreme = extreme.sort_values("signed_return", key=abs, ascending=False)
        print(f"\n=== Extreme |signed_return| > 25% at h=20 (likely rollover artifacts or genuine moves) ===")
        print(extreme[["symbol", "date", "direction", "subtype", "confidence",
                       "entry_close", "signed_return"]].head(20).to_string(index=False))

    # ---- Top/Bottom symbols by EV at h=20 ----
    sym_ev = summary_by(df20, ["symbol"])
    sym_ev = sym_ev[sym_ev["n"] >= 10].sort_values("avg_signed_ret_pct", ascending=False)
    if not sym_ev.empty:
        print(f"\n=== Top-3 symbols by EV at h=20 (n ≥ 10) ===")
        print(sym_ev.head(3).to_string(index=False))
        print(f"\n=== Bottom-3 symbols by EV at h=20 (n ≥ 10) ===")
        print(sym_ev.tail(3).to_string(index=False))

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
