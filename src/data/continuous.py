"""OI/volume main-contract continuous synthesis for CN futures.

The quant-cli store holds individual contract months (``SHFE.cu2509``) but
no provider continuous series (the legacy feed's ``cu0``).  This module
derives a main-contract continuous series strategy-side, read-only:

  - **Selection metric**: settlement ``open_interest`` when any active
    contract carries OI > 0 on that date, daily ``volume`` otherwise
    (historical files were synced by a fetcher that did not map OI —
    recorded in doc/data_gaps_for_pipeline_2026-06-11.md; the volume
    fallback converges to pure OI as history is re-synced).
  - **No lookahead**: the main contract for trading day *d* is decided
    from the *prior* session's settlement metric.  The first session
    bootstraps on itself.
  - **Roll rule**: a challenger with a LATER expiry must beat the
    incumbent for ``confirm_days`` consecutive settlements; the switch
    takes effect the next session.  Earlier expiries never become main
    again (forward-only).  An incumbent with no bar on *d* (expired /
    delisted) forces an immediate roll.
  - **Intraday slicing**: a contract's intraday bars are assigned to
    trading days CN-style — night-session bars (period_end after 16:00,
    or before ~04:00 the next calendar morning) belong to the NEXT
    trading day — and each trading day's bars come from that day's main
    contract.  No price adjustment is applied (matches the legacy
    provider's unadjusted continuous).

CZCE filenames exist in both 4-digit (``CZCE.CF2509``) and legacy 3-digit
vt-symbol (``CF509.CZCE``) forms; months dedupe preferring the 4-digit
file.  The 3-digit year digit is interpreted in 2020-2029.
"""

from __future__ import annotations

import re
from bisect import bisect_left, bisect_right
from datetime import date, time
from pathlib import Path

import pandas as pd

_LEVEL_TO_FOLDER: dict[str, str] = {
    "D":     "daily",
    "60min": "hour",
    "15min": "min15",
    "5min":  "min5",
}

_COLUMNS = [
    "datetime", "open", "high", "low", "close",
    "volume", "turnover", "open_interest",
]

_NIGHT_START = time(16, 0)   # period_end after this → next trading day
_NIGHT_SPILL = time(4, 0)    # period_end before this → still night session

# Head-trim: leading dates whose main-contract volume is below this
# fraction of the synthesized series' median volume are dropped.
_LIQUIDITY_HEAD_FRAC = 0.05

# (root, exchange, product, confirm_days) → {date: month}
_SCHEDULE_CACHE: dict[tuple, dict[date, str]] = {}


# ---------------------------------------------------------------------------
# Contract discovery
# ---------------------------------------------------------------------------

def _canonical_month(digits: str) -> str:
    """'2509' → '202509'; '509' → '202509' (2020-2029 decade)."""
    if len(digits) == 4:
        return f"20{digits}"
    return f"202{digits}"


def discover_contracts(
    root: Path, folder: str, exchange: str, product: str
) -> dict[str, Path]:
    """Map canonical contract month (YYYYMM) → parquet path.

    Matches prefix form ``{EXCHANGE}.{product}{YYMM}`` and, for CZCE,
    the legacy suffix form ``{PRODUCT}{YMM}.CZCE``.  Option files
    (strike-suffixed) never match the fullmatch patterns.
    """
    d = Path(root) / folder
    if not d.is_dir():
        return {}

    prefix_re = re.compile(
        rf"{re.escape(exchange)}\.{re.escape(product)}(\d{{3,4}})"
    )
    suffix_re = (
        re.compile(rf"{re.escape(product)}(\d{{3,4}})\.CZCE")
        if exchange == "CZCE" else None
    )

    found: dict[str, tuple[int, Path]] = {}  # month → (digits_len, path)
    for p in d.glob("*.parquet"):
        stem = p.stem
        m = prefix_re.fullmatch(stem)
        if m is None and suffix_re is not None:
            m = suffix_re.fullmatch(stem)
        if m is None:
            continue
        digits = m.group(1)
        month = _canonical_month(digits)
        prev = found.get(month)
        if prev is None or len(digits) > prev[0]:  # prefer 4-digit file
            found[month] = (len(digits), p)
    return {month: path for month, (_, path) in found.items()}


# ---------------------------------------------------------------------------
# Main-contract schedule
# ---------------------------------------------------------------------------

def _load_daily_panel(
    root: Path, exchange: str, product: str
) -> dict[str, pd.DataFrame]:
    """month → daily df indexed by date, with the raw store columns."""
    panel: dict[str, pd.DataFrame] = {}
    for month, path in discover_contracts(root, "daily", exchange, product).items():
        df = pd.read_parquet(path)
        if df.empty:
            continue
        df = df.copy()
        # Drop close-only placeholder rows (far-month files carry rows
        # with OHLV = 0 and only a settlement close)
        df = df[(df[["open", "high", "low", "close"]] > 0).all(axis=1)]
        if df.empty:
            continue
        df["_date"] = pd.to_datetime(df["datetime"]).dt.date
        df = df.drop_duplicates(subset=["_date"], keep="last").set_index("_date")
        panel[month] = df
    return panel


def build_main_schedule(
    root: Path, exchange: str, product: str, *, confirm_days: int = 1
) -> dict[date, str]:
    """Per trading date, the canonical month of the main contract."""
    key = (str(root), exchange, product, confirm_days)
    cached = _SCHEDULE_CACHE.get(key)
    if cached is not None:
        return cached

    panel = _load_daily_panel(root, exchange, product)
    if not panel:
        _SCHEDULE_CACHE[key] = {}
        return {}

    all_dates: list[date] = sorted({d for df in panel.values() for d in df.index})

    def metric(d: date) -> dict[str, float]:
        oi = {m: float(df.loc[d, "open_interest"])
              for m, df in panel.items() if d in df.index}
        if any(v > 0 for v in oi.values()):
            return oi
        return {m: float(df.loc[d, "volume"])
                for m, df in panel.items() if d in df.index}

    last_date: dict[str, date] = {m: df.index.max() for m, df in panel.items()}

    sched: dict[date, str] = {}
    first = all_dates[0]
    m0 = metric(first)
    main = max(m0, key=m0.get)  # bootstrap on the first session itself
    sched[first] = main
    streak_month: str | None = None
    streak = 0

    for i in range(1, len(all_dates)):
        d, p = all_dates[i], all_dates[i - 1]
        active_d = {m for m, df in panel.items() if d in df.index}
        mp = metric(p)

        if d > last_date[main]:
            # incumbent truly expired/delisted — forced roll.  (A mere
            # one-day hole keeps the incumbent; the daily series just
            # skips that date.)
            later = [m for m in active_d if m > main] or sorted(active_d)
            scores = {m: mp.get(m, float("-inf")) for m in later}
            if all(v == float("-inf") for v in scores.values()):
                md = metric(d)
                scores = {m: md.get(m, float("-inf")) for m in later}
            main = max(scores, key=scores.get)
            streak_month, streak = None, 0
        else:
            challengers = {m for m in mp if m > main}
            if challengers and main in mp:
                leader = max(challengers, key=lambda m: mp[m])
                if mp[leader] > mp[main]:
                    streak = streak + 1 if streak_month == leader else 1
                    streak_month = leader
                    if streak >= confirm_days:
                        main = leader
                        streak_month, streak = None, 0
                else:
                    streak_month, streak = None, 0
            else:
                streak_month, streak = None, 0

        sched[d] = main

    _SCHEDULE_CACHE[key] = sched
    return sched


# ---------------------------------------------------------------------------
# Series synthesis
# ---------------------------------------------------------------------------

def _trading_date(ts: pd.Timestamp, sessions: list[date]) -> date | None:
    """CN trading day owning an intraday bar with period_end ``ts``."""
    t = ts.time()
    d = ts.date()
    if t > _NIGHT_START:
        idx = bisect_right(sessions, d)        # next session strictly after d
    elif t <= _NIGHT_SPILL:
        idx = bisect_left(sessions, d)         # next session on/after d
    else:
        return d
    return sessions[idx] if idx < len(sessions) else None


def _synthesize_daily(
    root: Path, exchange: str, product: str, sched: dict[date, str]
) -> pd.DataFrame:
    panel = _load_daily_panel(root, exchange, product)
    rows = []
    for d in sorted(sched):
        month = sched[d]
        df = panel.get(month)
        if df is None or d not in df.index:
            continue
        rows.append(df.loc[d, _COLUMNS])
    out = pd.DataFrame(rows).reset_index(drop=True)
    out["datetime"] = pd.to_datetime(out["datetime"])
    return out


def _synthesize_intraday(
    root: Path,
    exchange: str,
    product: str,
    level: str,
    sched: dict[date, str],
    sessions: list[date],
) -> pd.DataFrame:
    """``sessions`` must be the FULL session calendar (pre-trim) so that
    night bars from trimmed head dates map to their true trading day
    (absent from the trimmed ``sched``) instead of bisecting onto the
    first post-trim session."""
    folder = _LEVEL_TO_FOLDER[level]
    contracts = discover_contracts(root, folder, exchange, product)
    parts = []
    for month in sorted(set(sched.values())):
        path = contracts.get(month)
        if path is None:
            continue
        df = pd.read_parquet(path)
        if df.empty:
            continue
        df = df.copy()
        ts = pd.to_datetime(df["datetime"])
        tdates = [_trading_date(t, sessions) for t in ts]
        keep = [td is not None and sched.get(td) == month for td in tdates]
        part = df.loc[keep, _COLUMNS]
        if not part.empty:
            parts.append(part)
    if not parts:
        return pd.DataFrame(columns=_COLUMNS)
    out = pd.concat(parts, ignore_index=True)
    out["datetime"] = pd.to_datetime(out["datetime"])
    return out.sort_values("datetime").reset_index(drop=True)


def _resample_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    df = daily.copy()
    iso = df["datetime"].dt.isocalendar()
    rows = []
    for (_, _), g in df.groupby([iso["year"], iso["week"]], sort=True):
        rows.append({
            "datetime":      g["datetime"].iloc[-1],
            "open":          g["open"].iloc[0],
            "high":          g["high"].max(),
            "low":           g["low"].min(),
            "close":         g["close"].iloc[-1],
            "volume":        g["volume"].sum(),
            "turnover":      g["turnover"].sum(),
            "open_interest": g["open_interest"].iloc[-1],
        })
    return pd.DataFrame(rows, columns=_COLUMNS)


def synthesize_continuous(
    root: Path | str,
    exchange: str,
    product: str,
    level: str,
    *,
    confirm_days: int = 1,
) -> pd.DataFrame:
    """Continuous main-contract series in the raw store schema.

    Args:
        root: store root (folders daily/hour/min15/min5 under it).
        exchange: store exchange prefix (SHFE/DCE/CZCE/CFFEX/INE/GFEX).
        product: product code in the store's case (cu / IF / MA ...).
        level: BarStore level string ("D" / "W" / "60min" / "15min" / "5min").
        confirm_days: consecutive settlements a challenger must lead.

    Returns:
        DataFrame with the 8 store columns, naive datetimes, sorted.

    Raises:
        ValueError: if no contract files exist for the product.
    """
    root = Path(root)
    sched = build_main_schedule(
        root, exchange, product, confirm_days=confirm_days
    )
    if not sched:
        raise ValueError(
            f"No contract files found for {exchange}.{product} under {root}"
        )
    full_sessions = sorted(sched)
    daily = _synthesize_daily(root, exchange, product, sched)

    # Liquidity head-trim: early store coverage may lack the era's true
    # main contracts, leaving only illiquid far months (e.g. cu 2021 —
    # nominal coverage starts 2021 but 2021-expiry contracts are absent).
    # Trim leading dates until the main contract's volume reaches a
    # fraction of the series' median.
    floor = daily["volume"].median() * _LIQUIDITY_HEAD_FRAC
    liquid = daily["volume"] >= floor
    if liquid.any():
        start_idx = liquid.idxmax()
        start_date = daily["datetime"].iloc[start_idx].date()
        if start_idx > 0:
            daily = daily.iloc[start_idx:].reset_index(drop=True)
            sched = {d: m for d, m in sched.items() if d >= start_date}

    if level == "D":
        return daily
    if level == "W":
        return _resample_weekly(daily)
    if level in _LEVEL_TO_FOLDER:
        return _synthesize_intraday(
            root, exchange, product, level, sched, full_sessions
        )
    raise KeyError(
        f"Level {level!r} not supported for continuous synthesis. "
        f"Supported: ['D', 'W', '60min', '15min', '5min']"
    )
