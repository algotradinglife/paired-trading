"""Analyze options payoff from pre-collected OHLC JSON files.

Reads option JSON files from data/options/ (US) and data/options/cn/ (CN),
computes h=5/10/20 trading-day returns with optional 4-tick stop-loss logic,
and aggregates by: direction × higher_relation × OTM rank × horizon

4-tick stop model:
  stop_price = entry_premium − 4 × tick_size(underlying)
  stop detection: if daily bar low < stop_price → stopped out that day
  (daily low is an approximation; intraday stops may differ slightly)

Two file formats are handled automatically:
  old format: payload has 'signal_date' and 'otm_rank'
  new format: payload has 'contract_type'; signal_date inferred from first bar;
              OTM rank computed from strike ordering relative to signal entry_price

Usage:
  uv run python scripts/analyze_options_payoff.py
  uv run python scripts/analyze_options_payoff.py --market US
  uv run python scripts/analyze_options_payoff.py --market CN --direction bottom
  uv run python scripts/analyze_options_payoff.py --stop           # enable 4-tick stop
  uv run python scripts/analyze_options_payoff.py --otm-ranks 1 2 3 4
  uv run python scripts/analyze_options_payoff.py -o data/review/option_payoffs_full.csv
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from quant_data.models import BarData, ContractData, Exchange, Interval, OptionType, Product
from quant_data.storage import ParquetStorage

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SRC_DIR    = Path(__file__).resolve().parents[1]


def _default_review_dir() -> Path:
    """Default review dir; honors DERIVED_ROOT env var, falls back to src/data/review."""
    derived = os.environ.get("DERIVED_ROOT")
    if derived:
        return Path(derived) / "paired-trading" / "src-data-review"
    return SRC_DIR / "data" / "review"


REVIEW_DIR = _default_review_dir()

POOL_FILES_US = {
    "US_EQUITY": REVIEW_DIR / "rr_b_us_equity.csv",
    "US_MACRO":  REVIEW_DIR / "rr_b_us_macro.csv",
}
POOL_FILES_CN = {
    "CN_METAL": REVIEW_DIR / "rr_b_cn_metal.csv",
    "CN_AGRI":  REVIEW_DIR / "rr_b_cn_agri.csv",
}

OPTIONS_DIR_US = SRC_DIR / "data" / "options"
OPTIONS_DIR_CN = SRC_DIR / "data" / "options" / "cn"
_QUANT_DATA_ROOT = SRC_DIR / "data" / "quant"

# US symbol directories to scan (excludes cn/ and any stale kq_m_* dirs)
US_SYMBOL_DIRS = [
    "spy", "qqq", "iwm", "dia", "nvda", "xlf", "xlk", "gdx", "gld", "tlt",
]

HORIZONS = [5, 10, 20]

# ---------------------------------------------------------------------------
# 4-tick stop: option premium minimum fluctuation per underlying
# Keys are normalised underlying keys (from _normalize_underlying_key).
# Daily-bar low is used as intraday proxy: if low < stop → counted as stopped.
# ---------------------------------------------------------------------------
TICK_SIZES: dict[str, float] = {
    # SHFE
    "au": 0.02,   # gold  — yuan/gram
    "ag": 1.0,    # silver — yuan/kg
    "cu": 10.0,   # copper — yuan/ton
    "rb": 1.0,    # rebar  — yuan/ton
    "al": 5.0,    # aluminium
    "zn": 5.0,    # zinc
    "ni": 10.0,   # nickel
    # DCE
    "m":  0.5,    # soybean meal — yuan/ton
    "i":  0.5,    # iron ore     — yuan/ton
    "pg": 2.0,    # LPG
    "c":  1.0,    # corn
    "pp": 1.0,    # polypropylene
    "l":  1.0,    # LLDPE
    # CZCE
    "sr": 0.5,    # sugar     — yuan/ton
    "ma": 0.5,    # methanol  — yuan/ton
    "ta": 2.0,    # PTA       — yuan/ton
    "cf": 5.0,    # cotton    — yuan/ton
    "rm": 1.0,    # rapeseed meal
    "zc": 0.2,    # thermal coal — yuan/ton
    # US equity options — $0.01/share = $1/contract of 100 shares
    "spy":  0.01,
    "qqq":  0.01,
    "iwm":  0.01,
    "dia":  0.01,
    "nvda": 0.01,
    "xlf":  0.01,
    "xlk":  0.01,
    "gdx":  0.01,
    "gld":  0.01,
    "tlt":  0.01,
}

STOP_TICKS = 4   # Xiao framework: 4-tick stop on option premium


# ---------------------------------------------------------------------------
# Signal loading
# ---------------------------------------------------------------------------
def _load_signal_csvs(pool_files: dict[str, Path]) -> pd.DataFrame:
    frames = []
    for pool, path in pool_files.items():
        if not path.exists():
            continue
        df = pd.read_csv(path)
        df["pool"] = pool
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


# ---------------------------------------------------------------------------
# Option file loading
# ---------------------------------------------------------------------------
def _ts_to_date(ts: int) -> date:
    return datetime.fromtimestamp(ts, tz=timezone.utc).date()


def _infer_contract_type(contract: str) -> str:
    """Guess call/put from ticker string when not explicitly stored."""
    lower = contract.lower()
    if "p" in lower.split("c")[-1] if "c" in lower else "p" in lower:
        return "put"
    return "call"


def _bars_by_day(bars: list[dict]) -> list[tuple[date, list[dict]]]:
    """Group bars by calendar date (UTC), sorted ascending."""
    from collections import defaultdict
    day_map: dict[date, list[dict]] = defaultdict(list)
    for bar in bars:
        d = _ts_to_date(bar["time"])
        day_map[d].append(bar)
    return sorted(day_map.items())


def _stop_payoffs(
    bars: list[dict],
    entry_premium: float,
    tick_size: float,
    horizons: list[int],
    n_ticks: int = STOP_TICKS,
    stop_pct: float | None = None,
) -> dict:
    """Compute stop-aware returns using daily bar low as intraday proxy.

    stop_price = entry_premium - n_ticks * tick_size  (default)
    stop_price = entry_premium * (1 - stop_pct)       (when stop_pct given)
    """
    stop_price = (
        entry_premium * (1 - stop_pct)
        if stop_pct is not None
        else entry_premium - n_ticks * tick_size
    )
    result: dict = {"stop_price": round(stop_price, 6)}

    # Find first bar (1-indexed) where low < stop_price
    first_stop: int | None = None
    for i in range(1, len(bars)):
        low = bars[i].get("low")
        if low is not None and low > 0 and low < stop_price:
            first_stop = i
            break
    result["first_stop_day"] = first_stop

    for h in horizons:
        if len(bars) <= h:
            result[f"stop_h{h}_ret"] = None
            result[f"h{h}_stopped"]  = None
            continue
        stopped = first_stop is not None and first_stop <= h
        if stopped:
            exit_price = stop_price
        else:
            exit_price = bars[h].get("close") or bars[h].get("open")
            if not exit_price or exit_price <= 0:
                result[f"stop_h{h}_ret"] = None
                result[f"h{h}_stopped"]  = True if stopped else False
                continue
        result[f"stop_h{h}_ret"] = round((exit_price - entry_premium) / entry_premium, 6)
        result[f"h{h}_stopped"]  = stopped

    return result


def _stop_payoffs_days(
    day_groups: list[tuple[date, list[dict]]],
    entry_day_idx: int,
    entry_premium: float,
    tick_size: float,
    horizons: list[int],
    n_ticks: int = STOP_TICKS,
    stop_pct: float | None = None,
) -> dict:
    """Stop-payoff using intraday bars for precise detection, horizons in trading days.

    Scans all 15min/60min bars from entry_bar onward. Converts first-stop bar
    to a trading-day index by counting day boundaries.

    stop_price = entry_premium - n_ticks * tick_size  (default)
    stop_price = entry_premium * (1 - stop_pct)       (when stop_pct given)
    """
    stop_price = (
        entry_premium * (1 - stop_pct)
        if stop_pct is not None
        else entry_premium - n_ticks * tick_size
    )
    result: dict = {"stop_price": round(stop_price, 6)}

    # Build flat bar list and per-day cumulative bar counts from entry day
    flat_bars: list[dict] = []
    day_bar_ends: list[int] = []  # index in flat_bars of last bar of each day
    for d, day_bars in day_groups[entry_day_idx:]:
        flat_bars.extend(day_bars)
        day_bar_ends.append(len(flat_bars) - 1)

    # Find first bar after entry (index > 0) where low < stop_price
    first_stop_bar: int | None = None
    for i in range(1, len(flat_bars)):
        low = flat_bars[i].get("low")
        if low is not None and low > 0 and low < stop_price:
            first_stop_bar = i
            break

    # Convert bar index → trading day offset (0 = entry day)
    first_stop_day: int | None = None
    if first_stop_bar is not None:
        for day_offset, end_idx in enumerate(day_bar_ends):
            if first_stop_bar <= end_idx:
                first_stop_day = day_offset
                break

    result["first_stop_day"] = first_stop_day

    for h in horizons:
        target_day_offset = h  # day_groups[entry_day_idx + h]
        if target_day_offset >= len(day_bar_ends):
            result[f"stop_h{h}_ret"] = None
            result[f"h{h}_stopped"]  = None
            continue
        stopped = first_stop_day is not None and first_stop_day <= target_day_offset
        if stopped:
            exit_price = stop_price
        else:
            target_day_bars = day_groups[entry_day_idx + target_day_offset][1]
            exit_price = target_day_bars[-1].get("close")
            if not exit_price or exit_price <= 0:
                result[f"stop_h{h}_ret"] = None
                result[f"h{h}_stopped"]  = False
                continue
        result[f"stop_h{h}_ret"] = round((exit_price - entry_premium) / entry_premium, 6)
        result[f"h{h}_stopped"]  = stopped

    return result


def _load_option_files_intraday(
    options_dir: Path,
    tf: str,
    signals: pd.DataFrame,
    use_stop: bool = False,
    stop_pct: float | None = None,
) -> pd.DataFrame:
    """Load intraday option files aligned to signal dates.

    For each signal (underlying, date), scans matching option contract files
    whose bar range covers the signal date, finds the entry bar as the first
    bar with date >= signal_date, and computes payoffs in trading days.

    Returns DataFrame with same schema as _load_option_files plus
    pre-filled direction/higher_relation/entry_price/confidence columns.
    """
    from collections import defaultdict

    rows: list[dict] = []
    pattern = f"*_{tf}.json"

    # Build signal index: normalized_underlying_key → list of signal dicts
    sig_by_key: dict[str, list[dict]] = defaultdict(list)
    for _, s in signals.iterrows():
        key = _normalize_underlying_key(str(s.get("symbol", "")).lower())
        sig_by_key[key].append({
            "signal_date":     pd.to_datetime(s["date"]).date() if pd.notna(s.get("date")) else None,
            "direction":       s.get("direction"),
            "higher_relation": s.get("higher_relation"),
            "entry":           s.get("entry"),
            "confidence":      s.get("confidence"),
        })

    for f in sorted(options_dir.rglob(pattern)):
        try:
            payload = json.loads(f.read_text())
        except Exception:
            continue

        bars = payload.get("bars", [])
        if len(bars) < 5:
            continue

        underlying = str(payload.get("underlying", "")).lower()
        und_key    = _normalize_underlying_key(underlying)

        sigs = sig_by_key.get(und_key)
        if not sigs:
            continue

        expiry_str = payload.get("expiry")
        try:
            expiry = date.fromisoformat(str(expiry_str)[:10]) if expiry_str else None
        except ValueError:
            expiry = None

        raw_ct = payload.get("contract_type")
        if not raw_ct:
            ticker = str(payload.get("contract", "")).upper()
            raw_ct = ("put" if ("P" in ticker and ("P" in ticker.split("C")[-1]
                      if "C" in ticker else True)) else "call")

        strike   = float(payload.get("strike", 0))
        contract = payload.get("contract", "")

        day_groups = _bars_by_day(bars)
        if not day_groups:
            continue
        min_date = day_groups[0][0]
        max_date = day_groups[-1][0]

        for sig_meta in sigs:
            sig_date = sig_meta["signal_date"]
            if sig_date is None:
                continue
            # Contract must cover the signal date and not be expired
            if sig_date < min_date or sig_date > max_date:
                continue
            if expiry and sig_date > expiry:
                continue

            # Entry is next trading day after signal (signal confirmed at daily close)
            entry_day_idx: int | None = None
            for i, (d, _) in enumerate(day_groups):
                if d > sig_date:
                    entry_day_idx = i
                    break
            if entry_day_idx is None:
                continue

            entry_day_bars = day_groups[entry_day_idx][1]
            entry_bar      = entry_day_bars[0]
            entry_premium  = entry_bar.get("open") or entry_bar.get("close")
            if not entry_premium or entry_premium <= 0:
                continue

            row: dict = {
                "file":            f.name,
                "contract":        contract,
                "underlying":      underlying,
                "strike":          strike,
                "contract_type":   raw_ct,
                "expiry":          payload.get("expiry"),
                "signal_date":     sig_date,
                "otm_rank":        None,
                "entry_premium":   float(entry_premium),
                "n_bars":          len(bars),
                "direction":       sig_meta["direction"],
                "higher_relation": sig_meta["higher_relation"],
                "entry_price":     sig_meta["entry"],
                "confidence":      sig_meta["confidence"],
            }

            # Payoff at h trading days (using day close of last bar that day)
            for h in HORIZONS:
                target_idx = entry_day_idx + h
                if target_idx < len(day_groups):
                    last_bar = day_groups[target_idx][1][-1]
                    close_h  = last_bar.get("close")
                    row[f"h{h}_ret"] = (
                        (close_h - entry_premium) / entry_premium
                        if close_h and close_h > 0 else None
                    )
                else:
                    row[f"h{h}_ret"] = None

            all_highs = [
                b["high"]
                for _, day_b in day_groups[entry_day_idx:]
                for b in day_b
                if b.get("high") and b["high"] > 0
            ]
            row["max_ret"] = (
                (max(all_highs) - entry_premium) / entry_premium if all_highs else None
            )

            if use_stop:
                tick = TICK_SIZES.get(und_key)
                if tick is not None:
                    stop_data = _stop_payoffs_days(
                        day_groups, entry_day_idx, entry_premium, tick, HORIZONS,
                        stop_pct=stop_pct,
                    )
                    row.update(stop_data)
                else:
                    row["stop_price"]     = None
                    row["first_stop_day"] = None
                    for h in HORIZONS:
                        row[f"stop_h{h}_ret"] = None
                        row[f"h{h}_stopped"]  = None

            rows.append(row)

    return pd.DataFrame(rows)


def _load_option_files(
    options_dir: Path,
    tf: str = "daily",
    subdirs: list[str] | None = None,
    use_stop: bool = False,
    stop_pct: float | None = None,
) -> pd.DataFrame:
    """Scan options_dir for *_{tf}.json files and extract payoff records.

    subdirs: if given, only scan these specific subdirectories (e.g. US symbols).
    use_stop: if True, add 4-tick stop columns (stop_price, first_stop_day,
              stop_h{h}_ret, h{h}_stopped) using daily low as intraday proxy.
    Returns DataFrame with one row per option file.
    """
    rows: list[dict] = []
    pattern = f"*_{tf}.json"

    if subdirs:
        search_dirs = [options_dir / s for s in subdirs if (options_dir / s).is_dir()]
    else:
        search_dirs = [options_dir]

    def _file_priority(p: Path) -> tuple:
        parts = p.stem.split("_")
        if parts[-1] == tf:
            # Canonical (0 extras) < dated (1) < exchange-dated (2+)
            return (len(parts) - 2, p.name)
        return (0, p.name)

    all_files: list[Path] = []
    for d in search_dirs:
        all_files.extend(sorted(d.rglob(pattern), key=_file_priority))

    seen_contracts: set[tuple[str, str]] = set()

    for f in all_files:
        try:
            payload = json.loads(f.read_text())
        except Exception:
            continue

        bars = payload.get("bars", [])
        if not bars:
            continue

        # Entry premium: first bar's open, fall back to close
        entry_bar = bars[0]
        entry_premium = entry_bar.get("open") or entry_bar.get("close")
        if not entry_premium or entry_premium <= 0:
            continue

        # Infer contract_type when absent (old CN files use uppercase P/C in ticker)
        raw_ct = payload.get("contract_type")
        if not raw_ct:
            ticker = str(payload.get("contract", ""))
            raw_ct = "put" if ("P" in ticker.upper().split("C")[-1] if "C" in ticker.upper()
                               else "P" in ticker.upper()) else "call"

        # signal_date: from payload (old format) or first bar timestamp
        sig_date_raw = payload.get("signal_date")
        if sig_date_raw:
            try:
                sig_date = date.fromisoformat(str(sig_date_raw)[:10])
            except ValueError:
                sig_date = None
        else:
            sig_date = _ts_to_date(bars[0]["time"])

        # Deduplicate: skip dated/exchange variants when canonical was already loaded
        # (contract normalized: strip exchange suffix, uppercase)
        contract_norm = str(payload.get("contract", "")).split(".")[0].upper()
        dedup_key = (contract_norm, str(sig_date))
        if dedup_key in seen_contracts:
            continue
        seen_contracts.add(dedup_key)

        row: dict = {
            "file":          f.name,
            "contract":      payload.get("contract", ""),
            "underlying":    str(payload.get("underlying", "")).lower(),
            "strike":        float(payload.get("strike", 0)),
            "contract_type": raw_ct,
            "expiry":        payload.get("expiry"),
            "signal_date":   sig_date,
            "otm_rank":      payload.get("otm_rank"),  # None in new-format files
            "entry_premium": float(entry_premium),
            "n_bars":        len(bars),
        }

        # Payoff at h trading days (bar index h, since bars are daily)
        for h in HORIZONS:
            if len(bars) > h:
                close_h = bars[h].get("close")
                row[f"h{h}_ret"] = (
                    (close_h - entry_premium) / entry_premium
                    if close_h and close_h > 0 else None
                )
            else:
                row[f"h{h}_ret"] = None

        # Max return in window
        highs = [b["high"] for b in bars if b.get("high") and b["high"] > 0]
        row["max_ret"] = (max(highs) - entry_premium) / entry_premium if highs else None

        # 4-tick stop columns (only when requested)
        if use_stop:
            und_key = _normalize_underlying_key(str(payload.get("underlying", "")))
            tick = TICK_SIZES.get(und_key)
            if tick is not None:
                stop_data = _stop_payoffs(bars, entry_premium, tick, HORIZONS,
                                          stop_pct=stop_pct)
                row.update(stop_data)
            else:
                row["stop_price"]     = None
                row["first_stop_day"] = None
                for h in HORIZONS:
                    row[f"stop_h{h}_ret"] = None
                    row[f"h{h}_stopped"]  = None

        rows.append(row)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Join options with signals
# ---------------------------------------------------------------------------
def _normalize_underlying_key(s: str) -> str:
    """Produce a short lowercase key for matching: 'kq_m_shfe_au' → 'au', 'spy' → 'spy'."""
    s = s.lower()
    if s.startswith("kq_m_"):
        return s.split("_")[-1]
    return s.split("_")[-1] if "_" in s else s


def join_with_signals(
    opts: pd.DataFrame,
    signals: pd.DataFrame,
) -> pd.DataFrame:
    """Join option rows with signal metadata on (underlying_key, signal_date)."""
    if opts.empty or signals.empty:
        out = opts.copy()
        for col in ("direction", "higher_relation", "entry_price", "confidence"):
            if col not in out.columns:
                out[col] = None
        return out

    # Build join keys
    opts = opts.copy()
    opts["_key"] = opts["underlying"].apply(_normalize_underlying_key)

    sigs = signals.copy()
    sigs["_key"] = sigs["symbol"].str.lower().apply(_normalize_underlying_key)
    sigs["_date"] = pd.to_datetime(sigs["date"]).dt.date

    # Build multi-key lookup: exact date + ±3 day tolerance for new-format files
    # where first-bar date may differ from signal date due to holidays/weekends.
    # When two signals both fall within tolerance of the same option-file date,
    # keep the nearest one (smallest |delta|) to avoid silent misattribution.
    from datetime import timedelta
    sig_lookup: dict[tuple, dict] = {}
    sig_dist:   dict[tuple, int]  = {}   # tracks |delta| of current winner
    for _, s in sigs.iterrows():
        meta = {
            "direction":       s.get("direction"),
            "higher_relation": s.get("higher_relation"),
            "entry":           s.get("entry"),
            "confidence":      s.get("confidence"),
        }
        base = s["_date"]
        for delta in range(-3, 4):
            key      = (s["_key"], base + timedelta(days=delta))
            abs_dist = abs(delta)
            if key not in sig_dist or abs_dist < sig_dist[key]:
                sig_lookup[key] = meta
                sig_dist[key]   = abs_dist

    directions, relations, entries, confs = [], [], [], []
    for _, row in opts.iterrows():
        key = (row["_key"], row["signal_date"])
        meta = sig_lookup.get(key, {})
        directions.append(meta.get("direction"))
        relations.append(meta.get("higher_relation"))
        entries.append(meta.get("entry"))
        confs.append(meta.get("confidence"))

    opts["direction"]       = directions
    opts["higher_relation"] = relations
    opts["entry_price"]     = entries
    opts["confidence"]      = confs
    return opts.drop(columns=["_key"])


# ---------------------------------------------------------------------------
# OTM rank assignment for new-format files (no stored otm_rank)
# ---------------------------------------------------------------------------
def assign_otm_ranks(df: pd.DataFrame) -> pd.DataFrame:
    """For rows without otm_rank, compute it from strike ordering per signal group.

    call: rank = position of strike among strikes > entry_price, sorted ascending
    put:  rank = position of strike among strikes < entry_price, sorted descending

    Ranks are relative to the loaded (tradeable) chain only. Strikes with no
    option bars — typically illiquid — are absent, so rank 1 reflects the
    nearest liquid OTM strike rather than the nearest strike in the full listing.
    """
    df = df.copy()
    if "entry_price" not in df.columns:
        return df
    needs_rank = df["otm_rank"].isna() & df["entry_price"].notna()

    if not needs_rank.any():
        return df

    groups = df[needs_rank].groupby(
        ["underlying", "signal_date", "contract_type", "expiry"],
        dropna=False,
    )

    rank_map: dict[int, int] = {}
    for _, grp in groups:
        ct = grp["contract_type"].iloc[0]
        ep = grp["entry_price"].iloc[0]
        if ep is None:
            continue
        if ct == "call":
            otm = grp[grp["strike"] > ep].sort_values("strike")
        else:
            otm = grp[grp["strike"] < ep].sort_values("strike", ascending=False)
        for rank, (idx, _) in enumerate(otm.iterrows(), start=1):
            rank_map[idx] = rank

    for idx, rank in rank_map.items():
        df.at[idx, "otm_rank"] = rank

    return df


# ---------------------------------------------------------------------------
# Aggregation and report
# ---------------------------------------------------------------------------
def _ci95(x: pd.Series) -> tuple[float, float]:
    x = x.dropna()
    if len(x) < 3:
        return float("nan"), float("nan")
    lo, hi = stats.t.interval(0.95, df=len(x) - 1, loc=x.mean(), scale=stats.sem(x))
    return float(lo), float(hi)


def aggregate_report(
    df: pd.DataFrame,
    horizons: list[int] = HORIZONS,
    otm_ranks: list[int] | None = None,
    use_stop: bool = False,
) -> pd.DataFrame:
    """Aggregate by direction × relation × otm_rank × horizon.

    Returns tidy DataFrame with columns:
      direction, higher_relation, otm_rank, contract_type,
      horizon, n, mean_ret, median_ret, ci_lo, ci_hi, pct_positive
      [if use_stop]: stop_rate, mean_stop_ret, mean_actual_ret
    """
    df = df[df["direction"].notna() & df["higher_relation"].notna()].copy()
    df["otm_rank"] = pd.to_numeric(df["otm_rank"], errors="coerce")

    if otm_ranks:
        df = df[df["otm_rank"].isin(otm_ranks)]

    rows: list[dict] = []
    for (dirn, rel, rank, ct), grp in df.groupby(
        ["direction", "higher_relation", "otm_rank", "contract_type"],
        dropna=False,
    ):
        for h in horizons:
            col = f"h{h}_ret"
            vals = grp[col].dropna()
            if vals.empty:
                continue
            lo, hi = _ci95(vals)
            row: dict = {
                "direction":       dirn,
                "higher_relation": rel,
                "otm_rank":        rank,
                "contract_type":   ct,
                "horizon":         h,
                "n":               len(vals),
                "mean_ret":        round(vals.mean(), 4),
                "median_ret":      round(vals.median(), 4),
                "ci_lo":           round(lo, 4),
                "ci_hi":           round(hi, 4),
                "pct_positive":    round((vals > 0).mean(), 3),
            }
            if use_stop:
                stop_col  = f"stop_h{h}_ret"
                stop_flag = f"h{h}_stopped"
                if stop_col in grp.columns:
                    svals = grp[stop_col].dropna()
                    sflag = grp[stop_flag].dropna()
                    row["stop_rate"]      = round(sflag.mean(), 3) if not sflag.empty else None
                    row["mean_stop_ret"]  = round(svals.mean(), 4) if not svals.empty else None
                    slo, shi = _ci95(svals)
                    row["stop_ci_lo"]  = round(slo, 4)
                    row["stop_ci_hi"]  = round(shi, 4)
                    row["stop_pct_pos"] = round((svals > 0).mean(), 3) if not svals.empty else None
            rows.append(row)

    return pd.DataFrame(rows)


def print_report(agg: pd.DataFrame, title: str = "") -> None:
    if title:
        print(f"\n{'='*70}")
        print(f"  {title}")
        print(f"{'='*70}")

    if agg.empty:
        print("  (no data)")
        return

    has_stop = "stop_rate" in agg.columns

    key_combos = (
        agg[["direction", "higher_relation"]]
        .drop_duplicates()
        .sort_values(["direction", "higher_relation"])
    )
    for _, combo in key_combos.iterrows():
        dirn = combo["direction"]
        rel  = combo["higher_relation"]
        sub  = agg[(agg["direction"] == dirn) & (agg["higher_relation"] == rel)]
        print(f"\n  {dirn} × {rel}")
        if has_stop:
            print(f"  {'rank':>4}  {'type':>4}  {'h':>3}  {'n':>4}  "
                  f"{'mean':>7}  {'CI95(raw)':>18}  {'%>0':>5}  "
                  f"{'stop%':>5}  {'stop_ret':>8}  {'stop_CI95':>18}  {'s%>0':>5}")
            print(f"  {'-'*100}")
        else:
            print(f"  {'rank':>4}  {'type':>4}  {'h':>3}  {'n':>4}  "
                  f"{'mean':>7}  {'median':>7}  {'CI95':>18}  {'%>0':>5}")
            print(f"  {'-'*65}")
        for _, r in sub.sort_values(["otm_rank", "contract_type", "horizon"]).iterrows():
            ci = f"[{r['ci_lo']:+.3f}, {r['ci_hi']:+.3f}]"
            if has_stop:
                s_pct  = f"{r['stop_rate']:.1%}"  if pd.notna(r.get("stop_rate")) else "  N/A"
                s_ret  = f"{r['stop_ret']:+.3f}" if "stop_ret" in r and pd.notna(r.get("stop_ret")) else "     N/A"
                # Use mean_stop_ret column
                mean_sr = r.get("mean_stop_ret")
                s_ret  = f"{mean_sr:+.3f}" if pd.notna(mean_sr) else "     N/A"
                s_ci   = f"[{r['stop_ci_lo']:+.3f},{r['stop_ci_hi']:+.3f}]" if pd.notna(r.get("stop_ci_lo")) else "      N/A"
                s_pos  = f"{r['stop_pct_pos']:.1%}" if pd.notna(r.get("stop_pct_pos")) else "  N/A"
                print(f"  {r['otm_rank']:>4.0f}  {r['contract_type']:>4}  "
                      f"{r['horizon']:>3}  {r['n']:>4}  "
                      f"{r['mean_ret']:>+7.3f}  {ci:>18}  {r['pct_positive']:>5.1%}  "
                      f"{s_pct:>5}  {s_ret:>8}  {s_ci:>18}  {s_pos:>5}")
            else:
                print(f"  {r['otm_rank']:>4.0f}  {r['contract_type']:>4}  "
                      f"{r['horizon']:>3}  {r['n']:>4}  "
                      f"{r['mean_ret']:>+7.3f}  {r['median_ret']:>+7.3f}  "
                      f"{ci:>18}  {r['pct_positive']:>5.1%}")


# ---------------------------------------------------------------------------
# Parquet-backed option loading
# ---------------------------------------------------------------------------
def _bar_data_to_dict(bar: BarData) -> dict:
    """Convert BarData to the bar dict format used by payoff functions."""
    return {
        "time":   int(bar.datetime.replace(tzinfo=timezone.utc).timestamp()),
        "open":   bar.open_price,
        "high":   bar.high_price,
        "low":    bar.low_price,
        "close":  bar.close_price,
        "volume": bar.volume,
    }


def _load_underlying_close(
    storage: ParquetStorage,
    underlying_vt: str,
    signal_date,
) -> float | None:
    """Return the daily close of the underlying on or just before signal_date.

    underlying_vt: e.g. 'au0.SHFE', 'rb0.SHFE', 'SR0.CZCE'
    Returns None if no bar data found.
    """
    parts = underlying_vt.split(".")
    if len(parts) != 2:
        return None
    symbol, exchange_str = parts
    try:
        exchange = Exchange(exchange_str)
    except ValueError:
        return None

    start = datetime.combine(signal_date, datetime.min.time()) - timedelta(days=10)
    end   = datetime.combine(signal_date, datetime.min.time()) + timedelta(days=1)

    try:
        df = storage.load_bar_data(symbol, exchange, Interval.DAILY, start=start, end=end)
    except Exception:
        return None

    if df.empty:
        return None

    dts = pd.to_datetime(df["datetime"])
    if dts.dt.tz is not None:
        dts = dts.dt.tz_convert("UTC").dt.tz_localize(None)
    sig_dt = datetime.combine(signal_date, datetime.max.time())
    mask = dts <= sig_dt
    if not mask.any():
        return None
    idx = mask.values.nonzero()[0][-1]
    return float(df["close_price"].iloc[idx])


def _load_option_rows_parquet(
    storage: ParquetStorage,
    portfolios: list[str],
    exchange: Exchange,
    interval: Interval,
    signals: pd.DataFrame,
    use_stop: bool = False,
    stop_pct: float | None = None,
) -> pd.DataFrame:
    """Load option payoff rows from ParquetStorage, aligned to signal dates.

    For each signal (portfolio, signal_date), finds contracts in the registry
    that cover the signal date, loads their bars, and computes payoffs starting
    from the first bar after the signal date.

    Returns a DataFrame with the same schema as _load_option_files (one row
    per contract × signal match).
    """
    from collections import defaultdict

    rows: list[dict] = []

    # Build signal index: portfolio_key → list of signal dicts
    sig_by_key: dict[str, list[dict]] = defaultdict(list)
    for _, s in signals.iterrows():
        key = _normalize_underlying_key(str(s.get("symbol", "")).lower())
        sig_by_key[key].append({
            "signal_date":     pd.to_datetime(s["date"]).date() if pd.notna(s.get("date")) else None,
            "direction":       s.get("direction"),
            "higher_relation": s.get("higher_relation"),
            "entry":           s.get("entry"),
            "confidence":      s.get("confidence"),
        })

    for portfolio in portfolios:
        und_key = _normalize_underlying_key(portfolio.lower())
        sigs = sig_by_key.get(und_key, [])
        if not sigs:
            continue

        contracts = storage.load_contract_data(
            exchange=exchange,
            product=Product.OPTION,
            option_portfolio=portfolio.upper(),
        )
        if not contracts:
            continue

        for contract in contracts:
            bars_df = storage.load_bar_data(
                contract.symbol, exchange, interval,
                start=datetime(2000, 1, 1), end=datetime(2100, 1, 1),
            )
            if len(bars_df) < 5:
                continue
            dts = pd.to_datetime(bars_df["datetime"])
            if dts.dt.tz is None:
                dts = dts.dt.tz_localize("UTC")
            else:
                dts = dts.dt.tz_convert("UTC")
            # Parquet stores datetime64[us]; divide microseconds → seconds
            ns_per_unit = {"ns": 10**9, "us": 10**6, "ms": 10**3, "s": 1}.get(
                getattr(dts.dtype, "unit", None)
                or (str(dts.dtype).split("[")[1].split(",")[0].split("]")[0]),
                10**6,
            )
            unix_ts = dts.astype("int64") // ns_per_unit
            bar_dicts = [
                {
                    "time":   int(unix_ts.iloc[i]),
                    "open":   float(bars_df["open_price"].iloc[i]),
                    "high":   float(bars_df["high_price"].iloc[i]),
                    "low":    float(bars_df["low_price"].iloc[i]),
                    "close":  float(bars_df["close_price"].iloc[i]),
                    "volume": float(bars_df["volume"].iloc[i]),
                }
                for i in range(len(bars_df))
            ]

            day_groups = _bars_by_day(bar_dicts)
            if not day_groups:
                continue
            min_date = day_groups[0][0]
            max_date = day_groups[-1][0]
            expiry_date = contract.option_expiry.date() if contract.option_expiry else None

            for sig_meta in sigs:
                sig_date = sig_meta["signal_date"]
                if sig_date is None:
                    continue
                # Need at least one bar after signal_date for entry
                if sig_date >= max_date:
                    continue
                if expiry_date and sig_date > expiry_date:
                    continue

                # Entry is next trading day after signal
                entry_day_idx: int | None = None
                for i, (d, _) in enumerate(day_groups):
                    if d > sig_date:
                        entry_day_idx = i
                        break
                if entry_day_idx is None:
                    continue

                # Discard if entry is too far from signal (contract didn't exist yet).
                # JSON path uses ±3 day tolerance for weekends/holidays; 5 days here
                # covers a long-weekend gap (e.g. Fri signal → Wed entry) without
                # accepting contracts that weren't tradeable near the signal date.
                if day_groups[entry_day_idx][0] - sig_date > timedelta(days=5):
                    continue

                entry_day_bars = day_groups[entry_day_idx][1]
                entry_bar = entry_day_bars[0]
                entry_premium = entry_bar.get("open") or entry_bar.get("close")
                if not entry_premium or entry_premium <= 0:
                    continue

                ct_str = contract.option_type.value if contract.option_type else "call"

                # Compute OTM rank from strike_step and underlying close on signal date
                otm_rank = None
                if contract.strike_step > 0 and contract.option_underlying:
                    underlying_close = _load_underlying_close(
                        storage, contract.option_underlying, sig_date
                    )
                    if underlying_close and underlying_close > 0:
                        ct_str_lower = ct_str.lower()
                        if ct_str_lower == "call":
                            raw_rank = round(
                                (contract.option_strike - underlying_close) / contract.strike_step
                            )
                        else:
                            raw_rank = round(
                                (underlying_close - contract.option_strike) / contract.strike_step
                            )
                        otm_rank = raw_rank if raw_rank >= 1 else None

                row: dict = {
                    "file":            f"{contract.symbol}.parquet",
                    "contract":        contract.symbol,
                    "underlying":      portfolio.lower(),
                    "strike":          contract.option_strike,
                    "contract_type":   ct_str,
                    "expiry":          expiry_date.isoformat() if expiry_date else None,
                    "signal_date":     sig_date,
                    "otm_rank":        otm_rank,
                    "entry_premium":   float(entry_premium),
                    "n_bars":          len(bar_dicts),
                    "direction":       sig_meta["direction"],
                    "higher_relation": sig_meta["higher_relation"],
                    "entry_price":     sig_meta["entry"],
                    "confidence":      sig_meta["confidence"],
                }

                for h in HORIZONS:
                    target_idx = entry_day_idx + h
                    if target_idx < len(day_groups):
                        last_bar = day_groups[target_idx][1][-1]
                        close_h = last_bar.get("close")
                        row[f"h{h}_ret"] = (
                            (close_h - entry_premium) / entry_premium
                            if close_h and close_h > 0 else None
                        )
                    else:
                        row[f"h{h}_ret"] = None

                all_highs = [
                    b["high"]
                    for _, day_b in day_groups[entry_day_idx:]
                    for b in day_b
                    if b.get("high") and b["high"] > 0
                ]
                row["max_ret"] = (
                    (max(all_highs) - entry_premium) / entry_premium if all_highs else None
                )

                if use_stop:
                    tick = TICK_SIZES.get(und_key)
                    if tick is not None:
                        stop_data = _stop_payoffs_days(
                            day_groups, entry_day_idx, entry_premium, tick, HORIZONS,
                            stop_pct=stop_pct,
                        )
                        row.update(stop_data)
                    else:
                        row["stop_price"] = None
                        row["first_stop_day"] = None
                        for h in HORIZONS:
                            row[f"stop_h{h}_ret"] = None
                            row[f"h{h}_stopped"] = None

                rows.append(row)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(
        description="Analyze pre-collected option OHLC payoffs"
    )
    ap.add_argument("--market", choices=["US", "CN", "all"], default="all",
                    help="Market to analyze (default: all)")
    ap.add_argument("--tf", default="daily",
                    help="Timeframe suffix to load (default: daily)")
    ap.add_argument("--direction", nargs="+", choices=["bottom", "top"],
                    default=None, metavar="DIR",
                    help="Filter by signal direction")
    ap.add_argument("--relation", nargs="+", default=None, metavar="REL",
                    help="Filter by higher_relation")
    ap.add_argument("--otm-ranks", nargs="+", type=int, default=None,
                    help="OTM ranks to include (default: all)")
    ap.add_argument("--stop", action="store_true", default=False,
                    help="Add stop columns (uses daily low as intraday proxy)")
    ap.add_argument("--stop-pct", type=float, default=None, metavar="PCT",
                    help="Stop as fraction of entry premium, e.g. 0.20 for 20%%. "
                         "Overrides 4-tick model when set.")
    ap.add_argument(
        "--source", choices=["json", "parquet"], default="json",
        help="Data source: 'json' (legacy files) or 'parquet' (quant-data store). Default: json",
    )
    ap.add_argument("-o", "--out", default=None,
                    help="Output CSV path (default: <review_dir>/option_payoffs_full.csv "
                         "where review_dir honors $DERIVED_ROOT/paired-trading/src-data-review "
                         "or falls back to src/data/review/)")
    args = ap.parse_args()

    out_path = Path(args.out) if args.out else REVIEW_DIR / "option_payoffs_full.csv"

    frames = []
    intraday = args.tf != "daily"

    stop_pct = args.stop_pct

    if args.market in ("US", "all"):
        print("Loading US option data...")
        if args.source == "parquet":
            storage = ParquetStorage(_QUANT_DATA_ROOT)
            signals_us = _load_signal_csvs(POOL_FILES_US)
            tf_interval = {
                "daily": Interval.DAILY,
                "60":    Interval.HOUR_1,
                "15":    Interval.MINUTE_15,
                "5":     Interval.MINUTE_5,
            }.get(args.tf, Interval.DAILY)
            opts_us = _load_option_rows_parquet(
                storage=storage,
                portfolios=[s.upper() for s in US_SYMBOL_DIRS],
                exchange=Exchange.NYSE,
                interval=tf_interval,
                signals=signals_us,
                use_stop=args.stop,
                stop_pct=stop_pct,
            )
        elif intraday:
            signals_us = _load_signal_csvs(POOL_FILES_US)
            opts_us = _load_option_files_intraday(
                OPTIONS_DIR_US, tf=args.tf, signals=signals_us,
                use_stop=args.stop, stop_pct=stop_pct,
            )
        else:
            opts_us = _load_option_files(
                OPTIONS_DIR_US, tf=args.tf, subdirs=US_SYMBOL_DIRS,
                use_stop=args.stop, stop_pct=stop_pct,
            )
            if not opts_us.empty:
                signals_us = _load_signal_csvs(POOL_FILES_US)
                opts_us = join_with_signals(opts_us, signals_us)
        if not opts_us.empty:
            opts_us = assign_otm_ranks(opts_us)
            opts_us["market"] = "US"
            print(f"  {len(opts_us)} option records loaded (US)")
            frames.append(opts_us)
        else:
            print("  No US option data found.")

    if args.market in ("CN", "all"):
        print("Loading CN option files...")
        if args.source == "parquet":
            storage = ParquetStorage(_QUANT_DATA_ROOT)
            signals_cn = _load_signal_csvs(POOL_FILES_CN)
            cn_exchange_groups = [
                (Exchange.SHFE, ["AU", "AG", "CU", "RB"]),
                (Exchange.DCE,  ["M", "I", "Y", "P", "J", "JM"]),
                (Exchange.CZCE, ["SR", "MA", "TA", "CF", "SA"]),
            ]
            cn_frames = []
            for cn_exchange, cn_portfolios in cn_exchange_groups:
                chunk = _load_option_rows_parquet(
                    storage=storage,
                    portfolios=cn_portfolios,
                    exchange=cn_exchange,
                    interval=Interval.DAILY,
                    signals=signals_cn,
                    use_stop=args.stop,
                    stop_pct=stop_pct,
                )
                if not chunk.empty:
                    cn_frames.append(chunk)
            opts_cn = pd.concat(cn_frames, ignore_index=True) if cn_frames else pd.DataFrame()
        elif intraday:
            signals_cn = _load_signal_csvs(POOL_FILES_CN)
            opts_cn = _load_option_files_intraday(
                OPTIONS_DIR_CN, tf=args.tf, signals=signals_cn,
                use_stop=args.stop, stop_pct=stop_pct,
            )
        else:
            opts_cn = _load_option_files(
                OPTIONS_DIR_CN, tf=args.tf, use_stop=args.stop, stop_pct=stop_pct,
            )
            if not opts_cn.empty:
                signals_cn = _load_signal_csvs(POOL_FILES_CN)
                opts_cn = join_with_signals(opts_cn, signals_cn)
        if not opts_cn.empty:
            if args.source != "parquet":
                opts_cn = assign_otm_ranks(opts_cn)
            opts_cn["market"] = "CN"
            print(f"  {len(opts_cn)} option records loaded (CN)")
            frames.append(opts_cn)
        else:
            print("  No CN option files found.")

    if not frames:
        print("No data found. Run fetch_options_ohlc*.py first.")
        sys.exit(1)

    df = pd.concat(frames, ignore_index=True)

    # Apply filters
    if args.direction:
        df = df[df["direction"].isin(args.direction)]
    if args.relation:
        df = df[df["higher_relation"].isin(args.relation)]

    # Matched vs unmatched signal context
    matched   = df["direction"].notna().sum()
    unmatched = df["direction"].isna().sum()
    mode_tag  = f"tf={args.tf}, {'intraday-aligned' if intraday else 'daily-join'}"
    print(f"\nTotal records: {len(df)}  (matched signal: {matched}, unmatched: {unmatched})  [{mode_tag}]")

    # Save raw payoff records
    df.to_csv(out_path, index=False)
    print(f"Saved: {out_path}")

    # Aggregate and report
    agg = aggregate_report(df, horizons=HORIZONS, otm_ranks=args.otm_ranks, use_stop=args.stop)

    if not agg.empty:
        agg_path = out_path.with_name(out_path.stem + "_agg.csv")
        agg.to_csv(agg_path, index=False)
        print(f"Saved aggregation: {agg_path}")

    if args.stop:
        if stop_pct is not None:
            print(f"\n  [stop model: {stop_pct*100:.0f}% of entry premium, intraday detection]")
        else:
            print(f"\n  [stop model: 4-tick ({STOP_TICKS} × tick_size), intraday detection]")

    # Print per-market
    for market in df["market"].unique() if "market" in df.columns else ["all"]:
        sub = df[df["market"] == market] if "market" in df.columns else df
        sub_agg = aggregate_report(sub, horizons=HORIZONS, otm_ranks=args.otm_ranks, use_stop=args.stop)
        print_report(sub_agg, title=f"{market} — option payoff by direction×relation×rank×horizon")

    # Summary: bottom×opposing mean h20 across ranks
    print(f"\n{'='*70}")
    print("  HEADLINE: bottom × opposing — mean h20 return by OTM rank")
    print(f"{'='*70}")
    bxo = df[(df["direction"] == "bottom") & (df["higher_relation"] == "opposing")]
    if bxo.empty:
        print("  (no bottom×opposing data)")
    else:
        for ct in ["call", "put"]:
            sub = bxo[bxo["contract_type"] == ct]
            if sub.empty:
                continue
            print(f"\n  {ct.upper()}S")
            ranked = sub.groupby("otm_rank")["h20_ret"].agg(
                n="count", mean="mean", median="median",
                pct_pos=lambda x: (x.dropna() > 0).mean()
            ).reset_index()
            print(ranked.to_string(index=False))


if __name__ == "__main__":
    main()
