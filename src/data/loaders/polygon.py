"""Polygon daily reference loader (architecture v0.3 Step 0).

Reads the current `data/raw/<symbol>_daily.json` format (polygon
aggregates JSON) and produces a fully-validated BarFrame.

Critical normalization: polygon stamps daily bars at the trading
calendar day's midnight ET (= period_START in our terms). This loader
re-stamps each bar to the exchange's session_close (period_END) using
exchange_calendars XNYS lookup — closing a leak vector by construction.

Step 0 scope: daily only, XNYS only. Intraday / weekly / CN futures
are Step 3.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from data import calendars
from data.bar_frame import BarFrame, canonical_payload_hash


def load_polygon_daily(
    path: Path,
    *,
    as_of: datetime | None = None,
    symbol_override: str | None = None,
) -> BarFrame:
    """Load a polygon daily JSON snapshot into a BarFrame.

    Args:
        path: filesystem path to `<symbol>_daily.json`.
        as_of: snapshot time. Defaults to the file mtime if not given —
            this matches the only knowable signal for static JSON files
            (no provider-side timestamp available).
        symbol_override: pass the canonical uppercase ticker explicitly.
            If omitted, the symbol is derived from the JSON's "symbol"
            field, falling back to the filename stem (with "_daily"
            stripped).

    Raises:
        FileNotFoundError, ValueError, json.JSONDecodeError on malformed
        input. CalendarNotSupportedError if XNYS becomes unavailable
        (shouldn't happen for Step 0).
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"polygon snapshot not found: {path}")

    raw_text = path.read_text()
    payload = json.loads(raw_text)
    bars = payload.get("bars")
    if not bars:
        raise ValueError(f"polygon snapshot {path.name} has no bars")

    # Determine symbol.
    symbol = symbol_override or payload.get("symbol")
    if not symbol:
        # filename stem like "spy_daily" → "spy"
        stem = path.stem
        if stem.endswith("_daily"):
            stem = stem[: -len("_daily")]
        symbol = stem
    symbol = symbol.upper()

    # Determine as_of. Falls back to file mtime — provider snapshot has
    # no embedded "fetched_at" we trust universally, though some files
    # carry "fetched_at_data_ts" (we record it as source_query metadata
    # rather than as_of to keep the contract simple).
    if as_of is None:
        as_of = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    elif as_of.tzinfo is None:
        raise ValueError("as_of must be tz-aware")

    df_raw = pd.DataFrame(bars)
    expected_raw = {"time", "open", "high", "low", "close"}
    missing = expected_raw - set(df_raw.columns)
    if missing:
        raise ValueError(
            f"polygon snapshot {path.name} missing columns: {missing}"
        )

    # Convert epoch → UTC datetime. Polygon stamps this at the calendar
    # day's midnight ET (period_start). We DON'T trust these timestamps
    # for downstream usage; we only use the date to look up the
    # session_close.
    df = df_raw.copy()
    period_start_utc = pd.to_datetime(df["time"], unit="s", utc=True)

    # For each bar, the trading session DATE is the local-ET date of
    # period_start_utc. Look up XNYS session_close for that date.
    et_dates = period_start_utc.dt.tz_convert("America/New_York").dt.date

    import exchange_calendars as _ecals
    _xnys = _ecals.get_calendar("XNYS")
    _cal_lower = _xnys.first_session.date()

    closes: list[pd.Timestamp | None] = []
    for d in et_dates:
        try:
            if not calendars.is_session("XNYS", d):
                raise ValueError(
                    f"polygon snapshot {path.name} references non-session "
                    f"date {d}. Snapshot may be corrupt or from a different "
                    f"calendar."
                )
            closes.append(pd.Timestamp(calendars.session_close("XNYS", d)))
        except _ecals.errors.DateOutOfBounds:
            if d < _cal_lower:
                closes.append(None)
            else:
                raise
    df["timestamp"] = closes
    df = df[df["timestamp"].notna()].copy()
    if df.empty:
        raise ValueError(
            f"polygon snapshot {path.name}: all bars are before the "
            f"exchange_calendars XNYS lower bound ({_cal_lower}). "
            f"Check the snapshot date range."
        )
    df["timestamp"] = pd.DatetimeIndex(df["timestamp"].tolist()).tz_convert("UTC")

    # Keep volume if present; drop polygon-specific extras (open_interest
    # etc are not in polygon daily; volume might be missing for some
    # snapshots — handle gracefully).
    keep_cols = ["timestamp", "open", "high", "low", "close"]
    if "volume" in df.columns:
        keep_cols.append("volume")
    df = df[keep_cols].sort_values("timestamp").reset_index(drop=True)

    # Codex P1 (2026-05-28): polygon may include the CURRENT day's
    # aggregate even if the session hasn't closed yet — its normalized
    # period_end (session_close) will then be AFTER as_of. Such bars
    # are not yet knowable at snapshot time; admitting them
    # reintroduces the look-ahead leak this loader exists to prevent.
    # Filter them out and warn loudly if any were dropped.
    as_of_pd = pd.Timestamp(as_of)
    pre_filter_n = len(df)
    df = df[df["timestamp"] <= as_of_pd].reset_index(drop=True)
    if df.empty:
        raise ValueError(
            f"polygon snapshot {path.name}: every bar's normalized "
            f"period_end is after as_of={as_of.isoformat()}. The snapshot "
            f"may have been pulled too early in the session for any bar "
            f"to be complete. (pre_filter_n={pre_filter_n})"
        )
    # Note: when the polygon snapshot contains a mid-session current-
    # day bar, it gets silently dropped here. Downstream callers must
    # rely on `last_completed_ts` (which reflects the latest CLOSED bar
    # after filtering) rather than `len(df)` of the raw JSON.

    # Sanity: after normalization, every timestamp must be at XNYS close
    # (we just set them so this should always hold — but verify the
    # invariant for defense in depth).
    cv = calendars.calendar_version_for("XNYS")

    payload_hash = canonical_payload_hash(df)
    last_completed_ts = df["timestamp"].iloc[-1].to_pydatetime()

    return BarFrame(
        df=df,
        provider="polygon",
        symbol=symbol,
        level="D",
        exchange="XNYS",
        calendar_version=str(cv),
        adjustment_mode="split_only",  # current backfill convention
        session_policy="regular",
        source_query=f"file://{path.resolve()}",
        as_of=as_of,
        last_completed_ts=last_completed_ts,
        payload_hash=payload_hash,
    )
