"""BarStore — adapter between the quant-cli flat Parquet store and BarFrame.

Reads OHLCV bars written by the quant-cli data layer (``quant sync``,
~/workspace/quant) and returns BarFrame objects with the same timestamp
contract the legacy quant-data pipeline produced, so detector calibration
carries over unchanged.

Store layout (flat, one file per symbol per interval):

    {root}/{daily,hour,min15,min5,weekly}/{FILENAME}.parquet

with the 8-column schema ``datetime`` (naive), ``open/high/low/close``,
``volume``, ``turnover``, ``open_interest``.

Timestamp semantics (and how they map to the legacy contract):

  - CN intraday: stored naive Beijing, period-END (minishare/tushare
    convention) -> localized Asia/Shanghai -> UTC.  Identical instants to
    the legacy store, which converted to naive UTC at fetch time.
  - CN + US daily/weekly: stored as naive midnight date markers -> labeled
    UTC midnight as-is (legacy behaviour; converting via Shanghai would
    shift the calendar date).  Exception: US daily is re-stamped to the
    exchange session close via exchange_calendars, matching the legacy
    loader.
  - US intraday: stored naive in the fetch host's local tz (Beijing),
    period-START (polygon epoch passed through ``datetime.fromtimestamp``)
    -> localized Asia/Shanghai -> UTC -> shifted +interval to period-END
    -> filtered to the NYSE regular session (period_end in (9:30, 16:00]
    ET; the new feed carries pre/post-market bars the legacy feed did not,
    which inflated H2 signal counts ~3x and flipped per-symbol EV signs —
    verified against the pa_us_60min QQQ baseline cell 2026-06-11).
    NOTE: the legacy store passed polygon start-stamps through unshifted
    (mislabelled as period_end), so US intraday timestamps here are
    +interval vs. the pre-migration data; expect baseline drift.  The shift
    is required for the as_of leak guard to be sound in live scoring.
    CAVEAT: localization is only correct for data synced on a host in
    Asia/Shanghai; see quant-cli ``fetchers/polygon.py``.

Filename mapping:

  - CN futures: ``{EXCHANGE}.{symbol}`` (e.g. SHFE.cu0, CZCE.MA0) — symbol
    case is the caller's (bar_loader emits lowercase for SHFE/DCE/INE,
    uppercase for CZCE/CFFEX, matching the store's files).
  - US: ``{SYMBOL}.AMEX`` (vnpy-style suffix used for all US tickers).

Writing/fetching is no longer this module's job — run ``quant sync`` in
~/workspace/quant instead (the legacy ``BarStore.update()`` is gone).
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from pathlib import Path

import pandas as pd

from data import calendars
from data.bar_frame import BarFrame, canonical_payload_hash

# ---------------------------------------------------------------------------
# Mapping tables
# ---------------------------------------------------------------------------

# macd-momentum level string → store folder
_LEVEL_TO_FOLDER: dict[str, str] = {
    "D":     "daily",
    "W":     "weekly",
    "60min": "hour",
    "15min": "min15",
    "5min":  "min5",
}

# MIC → store filename exchange prefix (CN futures)
_MIC_TO_EXCHANGE: dict[str, str] = {
    "XSHF": "SHFE",
    "XDCE": "DCE",
    "XZCE": "CZCE",
    "XCFE": "CFFEX",
    "XINE": "INE",
    "XGFE": "GFEX",
}

_US_MICS: frozenset[str] = frozenset({"XNYS", "XNAQ"})

_INTRADAY_LEVELS: frozenset[str] = frozenset({"60min", "15min", "5min"})

# US intraday stamps are polygon window STARTS; shift to period-end so the
# BarFrame contract (and the as_of leak guard) hold.  CN intraday is already
# period-end stamped (minishare/tushare convention) — no shift.
_LEVEL_TO_OFFSET: dict[str, pd.Timedelta] = {
    "60min": pd.Timedelta(hours=1),
    "15min": pd.Timedelta(minutes=15),
    "5min":  pd.Timedelta(minutes=5),
}

_LOCAL_TZ = "Asia/Shanghai"

# US regular session bounds. A bar is kept only when its FULL window
# [period_end - interval, period_end] lies inside the session — any bar
# straddling the 09:30 open mixes premarket trades into its OHLC.  For
# 60min this keeps period_end in (10:00, 16:00], which reproduces the
# legacy-feed pa_us_60min baseline cells exactly (IWM n=15 EV+0.633R,
# QQQ n=11; verified 2026-06-11).
_US_SESSION_OPEN = time(9, 30)
_US_SESSION_CLOSE = time(16, 0)


def _map_level(level: str) -> str:
    try:
        return _LEVEL_TO_FOLDER[level]
    except KeyError:
        supported = sorted(_LEVEL_TO_FOLDER.keys())
        raise KeyError(
            f"Level {level!r} not available in the quant-cli store. "
            f"Supported: {supported}"
        ) from None


def _map_filename(symbol: str, exchange: str) -> str:
    if exchange in _US_MICS:
        return f"{symbol.upper()}.AMEX"
    prefix = _MIC_TO_EXCHANGE.get(exchange)
    if prefix is None:
        supported = sorted(_MIC_TO_EXCHANGE.keys() | _US_MICS)
        raise KeyError(
            f"Exchange {exchange!r} not in BarStore exchange map. "
            f"Supported: {supported}"
        )
    return f"{prefix}.{symbol}"


# ---------------------------------------------------------------------------
# BarStore
# ---------------------------------------------------------------------------

class BarStore:
    """Reads the quant-cli Parquet store and returns BarFrame objects.

    Args:
        data_root: store root (e.g. ``/mnt/c/Users/hhusl/quant_data`` or a
            symlink such as ``src/data/quant``).

    Example::

        store = BarStore(Path("data/quant"))
        bf = store.load_barframe("SPY", "XNYS", "D")
    """

    def __init__(self, data_root: Path | str) -> None:
        self._root = Path(data_root)

    def load_barframe(
        self,
        symbol: str,
        exchange: str,
        level: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        as_of: datetime | None = None,
    ) -> BarFrame:
        """Read stored bars and return a BarFrame.

        Args:
            symbol: ticker or contract code (e.g. "SPY", "cu0", "MA0").
            exchange: MIC string (e.g. "XNYS", "XSHF").
            level: macd-momentum level string (e.g. "D", "60min").
            start: optional lower bound for the returned bars (UTC).
            end: optional upper bound for the returned bars (UTC).
            as_of: snapshot time for BarFrame.as_of (default: now UTC).
                   Mid-session bars whose period_end > as_of are dropped.

        Raises:
            KeyError: if exchange or level is not in the mapping tables.
            ValueError: if the data file is missing/empty or fails
                BarFrame validation.
        """
        folder = _map_level(level)
        fname = _map_filename(symbol, exchange)

        if as_of is None:
            as_of = datetime.now(timezone.utc)
        elif as_of.tzinfo is None:
            raise ValueError("as_of must be tz-aware (UTC)")

        path = self._root / folder / f"{fname}.parquet"
        if not path.exists():
            raise ValueError(
                f"No data found for {symbol}/{exchange}/{level}: {path}"
            )

        df = self._build_bar_df(pd.read_parquet(path), symbol, exchange, level)

        if start is not None:
            df = df[df["timestamp"] >= pd.Timestamp(start)]
        if end is not None:
            df = df[df["timestamp"] <= pd.Timestamp(end)]
        df = df.reset_index(drop=True)

        # Mid-session leak guard — drop bars whose period_end > as_of
        pre_filter_n = len(df)
        df = df[df["timestamp"] <= pd.Timestamp(as_of)].reset_index(drop=True)
        if df.empty:
            raise ValueError(
                f"quant store {symbol}/{exchange}/{level}: no bars remain "
                f"(pre-as_of n={pre_filter_n}, as_of={as_of.isoformat()}, "
                f"start={start}, end={end})."
            )

        return BarFrame(
            df=df,
            provider="quant_data",
            symbol=symbol.upper(),
            level=level,
            exchange=exchange,
            calendar_version=self._calendar_version(exchange),
            adjustment_mode="none",
            session_policy="regular",
            source_query=f"quant_cli://{folder}/{fname}",
            as_of=as_of,
            last_completed_ts=df["timestamp"].iloc[-1].to_pydatetime(),
            payload_hash=canonical_payload_hash(df),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_bar_df(
        df_raw: pd.DataFrame,
        symbol: str,
        exchange: str,
        level: str,
    ) -> pd.DataFrame:
        """Convert a quant-cli store DataFrame to BarFrame's expected format."""
        df = df_raw.copy()

        if not pd.api.types.is_datetime64_any_dtype(df["datetime"]):
            df["datetime"] = pd.to_datetime(df["datetime"])

        if level in _INTRADAY_LEVELS:
            # Naive Beijing wall-clock → UTC (see module docstring)
            df["datetime"] = (
                df["datetime"].dt.tz_localize(_LOCAL_TZ).dt.tz_convert("UTC")
            )
            if exchange in _US_MICS:
                df["datetime"] = df["datetime"] + _LEVEL_TO_OFFSET[level]
                # The polygon feed includes pre/post-market bars the legacy
                # feed did not (they inflated H2 signal counts ~3x and
                # flipped per-symbol EV signs). Keep only bars fully inside
                # the regular session — see _US_SESSION_OPEN note. The close
                # bound is calendar-aware (13:00 ET on NYSE half-days).
                end_et = df["datetime"].dt.tz_convert("America/New_York")
                start_t = (end_et - _LEVEL_TO_OFFSET[level]).dt.time
                close_t = BarStore._us_session_close_times(end_et)
                df = df[
                    (start_t >= _US_SESSION_OPEN) & (end_et.dt.time <= close_t)
                ].copy()
        elif exchange in _US_MICS and level == "D":
            df["datetime"] = BarStore._us_daily_session_close(df["datetime"], exchange)
            df = df[df["datetime"].notna()].copy()
            if df.empty:
                raise ValueError(
                    f"All bars for {symbol}/{exchange}/{level} were dropped "
                    f"during calendar session_close mapping (all OOB or "
                    f"non-session dates)."
                )
            df["datetime"] = pd.DatetimeIndex(df["datetime"]).tz_convert("UTC")
        else:
            # Daily/weekly date markers: label the naive midnight as UTC
            df["datetime"] = df["datetime"].dt.tz_localize("UTC")

        df = df.rename(columns={"datetime": "timestamp"})

        keep = ["timestamp", "open", "high", "low", "close", "volume", "open_interest"]
        df = df[[c for c in keep if c in df.columns]]

        for col in ("open", "high", "low", "close"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)

        if df.empty:
            raise ValueError(
                f"No valid price rows remain for {symbol}/{exchange}/{level} "
                f"after cleaning."
            )

        return (
            df.sort_values("timestamp")
            .drop_duplicates(subset=["timestamp"], keep="last")
            .reset_index(drop=True)
        )

    @staticmethod
    def _us_session_close_times(end_et: pd.Series) -> pd.Series:
        """Per-bar regular-session close time (ET) for the bar's ET date.

        Uses the exchange calendar so half-days close at 13:00 ET; bars on
        non-session dates get a sentinel that drops them.
        """
        close_by_date: dict = {}
        for d in end_et.dt.date.unique():
            try:
                if calendars.is_session("XNYS", d):
                    close_utc = pd.Timestamp(calendars.session_close("XNYS", d))
                    close_by_date[d] = (
                        close_utc.tz_convert("America/New_York").time()
                    )
                else:
                    close_by_date[d] = time(0, 0)  # non-session: drop all
            except Exception:
                close_by_date[d] = _US_SESSION_CLOSE  # OOB dates: fixed bound
        return end_et.dt.date.map(close_by_date)

    @staticmethod
    def _us_daily_session_close(dts: pd.Series, exchange: str) -> list:
        """Map naive trade-date markers to exchange session-close timestamps.

        Non-session dates (weekend/holiday) map to None and are dropped by
        the caller, same as the legacy loader.
        """
        import exchange_calendars as _ecals

        mic = "XNYS"  # NYSE and NASDAQ share the same session calendar
        cal = _ecals.get_calendar(mic)
        cal_lower = cal.first_session.date()
        cal_upper = cal.last_session.date()

        timestamps: list[pd.Timestamp | None] = []
        for dt in dts:
            date_obj = pd.Timestamp(dt).date()
            try:
                if not calendars.is_session(mic, date_obj):
                    timestamps.append(None)
                    continue
                timestamps.append(
                    pd.Timestamp(calendars.session_close(mic, date_obj))
                )
            except _ecals.errors.DateOutOfBounds:
                if date_obj < cal_lower:
                    timestamps.append(None)  # historic OOB — drop
                else:
                    raise RuntimeError(
                        f"Bar date {date_obj} exceeds exchange_calendars "
                        f"{mic} upper bound {cal_upper}. "
                        f"Run `pip install --upgrade exchange-calendars`."
                    ) from None
        return timestamps

    @staticmethod
    def _calendar_version(exchange: str) -> str:
        if exchange in _US_MICS:
            try:
                return str(calendars.calendar_version_for("XNYS"))
            except Exception:
                return "XNYS-unknown"
        return f"quant_cli+{exchange}"
