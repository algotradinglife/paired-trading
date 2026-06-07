"""BarStore — adapter between quant-data's ParquetStorage and BarFrame.

Reads OHLCV bars written by quant-data (Minishare/Polygon feeds) and
returns them as BarFrame objects, applying the correct period_end
timestamp semantics and column-name mapping.

Design notes:
  - No existing macd-momentum files are modified; this is a pure addition.
  - `provider="quant_data"` and `adjustment_mode="none"` because
    Minishare/Polygon data via quant-data is raw (no split adjustment).
  - Daily US bars (NYSE/NASDAQ): quant-data stores the bar datetime as
    market-close UTC; we confirm period_end via exchange_calendars so the
    timestamp contract is the same as the alphavantage loader.
  - Intraday and non-US bars: the stored datetime IS the period_end —
    passed through directly.
  - Column mapping: quant-data → BarFrame
      datetime        → timestamp   (tz-aware UTC)
      open_price      → open
      high_price      → high
      low_price       → low
      close_price     → close
      volume          → volume      (kept as-is)
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from data import calendars
from data.bar_frame import BarFrame, canonical_payload_hash
from quant_data.models import Exchange as QExchange, Interval
from quant_data.storage.parquet import ParquetStorage

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Exchange / interval mappings
# ---------------------------------------------------------------------------

# macd-momentum MIC string → quant-data Exchange enum
_EXCHANGE_MAP: dict[str, QExchange] = {
    "XNYS": QExchange.NYSE,
    "XNAQ": QExchange.NASDAQ,
    "XSHG": QExchange.SSE,
    "XSHE": QExchange.SZSE,
    "XSHF": QExchange.SHFE,
    "XDCE": QExchange.DCE,
    "XZCE": QExchange.CZCE,
    "XCFE": QExchange.CFFEX,
    "XINE": QExchange.INE,
    "XGFE": QExchange.GFEX,
}

# Reverse map for logging / source_query construction
_QEXCHANGE_TO_MIC: dict[QExchange, str] = {v: k for k, v in _EXCHANGE_MAP.items()}

# macd-momentum level string → quant-data Interval enum
_LEVEL_TO_INTERVAL: dict[str, Interval] = {
    "D":     Interval.DAILY,
    "W":     Interval.WEEKLY,
    "60min": Interval.HOUR_1,
    "4h":    Interval.HOUR_4,
    "30min": Interval.MINUTE_30,
    "15min": Interval.MINUTE_15,
    "5min":  Interval.MINUTE_5,
    "1min":  Interval.MINUTE_1,
}
_INTERVAL_TO_LEVEL: dict[Interval, str] = {v: k for k, v in _LEVEL_TO_INTERVAL.items()}

# US exchanges that use exchange_calendars for period_end timestamp derivation
_US_EXCHANGES: frozenset[QExchange] = frozenset({QExchange.NYSE, QExchange.NASDAQ})


# ---------------------------------------------------------------------------
# Datafeed factory
# ---------------------------------------------------------------------------

def _make_datafeed(exchange: QExchange):
    """Return the appropriate datafeed instance for the given exchange."""
    if exchange in _US_EXCHANGES:
        from quant_data.datafeed import PolygonDatafeed
        return PolygonDatafeed()
    else:
        from quant_data.datafeed import MinishareDatafeed
        return MinishareDatafeed()


# ---------------------------------------------------------------------------
# BarStore
# ---------------------------------------------------------------------------

class BarStore:
    """Reads quant-data's ParquetStorage and returns BarFrame objects.

    Args:
        data_root: directory passed to ParquetStorage — should be the
            same root used when writing data (e.g. ``./data/quant``).

    Example::

        store = BarStore(Path("data/quant"))
        bf = store.load_barframe("SPY", "XNYS", "D")
        store.update("SPY", "XNYS", "D",
                     start=datetime(2020, 1, 1, tzinfo=timezone.utc))
    """

    def __init__(self, data_root: Path | str) -> None:
        self._storage = ParquetStorage(data_root)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

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
            symbol: ticker or contract code (e.g. "SPY", "RB2501").
            exchange: MIC string matching _EXCHANGE_MAP (e.g. "XNYS").
            level: macd-momentum level string (e.g. "D", "60min").
            start: optional lower bound for the returned bars (UTC).
            end: optional upper bound for the returned bars (UTC).
            as_of: snapshot time for BarFrame.as_of (default: now UTC).
                   Mid-session bars whose period_end > as_of are dropped.

        Returns:
            BarFrame with period_end timestamps and provider="quant_data".

        Raises:
            KeyError: if exchange or level is not in the mapping tables.
            ValueError: if the stored data is empty or fails BarFrame validation.
        """
        q_exchange = self._map_exchange(exchange)
        interval = self._map_level(level)

        if as_of is None:
            as_of = datetime.now(timezone.utc)
        elif as_of.tzinfo is None:
            raise ValueError("as_of must be tz-aware (UTC)")

        df_raw = self._storage.load_bar_data(
            symbol, q_exchange, interval,
            start=start or datetime.min,
            end=end or datetime.max,
        )

        if isinstance(df_raw, type(iter([]))):
            # chunk_size was not set so we should have a DataFrame, but guard anyway
            import itertools
            df_raw = pd.concat(list(df_raw), ignore_index=True)

        if df_raw.empty:
            raise ValueError(
                f"No data found for {symbol}/{exchange}/{level} in "
                f"{self._storage._root}"
            )

        df = self._build_bar_df(df_raw, symbol, exchange, level, interval)

        # Mid-session leak guard — drop bars whose period_end > as_of
        pre_filter_n = len(df)
        df = df[df["timestamp"] <= pd.Timestamp(as_of)].reset_index(drop=True)
        if df.empty:
            raise ValueError(
                f"quant_data {symbol}/{exchange}/{level}: every bar's "
                f"period_end is after as_of={as_of.isoformat()} "
                f"(pre_filter_n={pre_filter_n})."
            )

        payload_hash = canonical_payload_hash(df)
        last_completed_ts = df["timestamp"].iloc[-1].to_pydatetime()

        # calendar_version: use exchange_calendars for US; synthetic string
        # for CN (quant-data does not use exchange_calendars internally).
        cal_version = self._calendar_version(exchange, level)

        # session_policy: quant-data fetches regular-session bars only
        session_policy = "regular"

        source_query = (
            f"quant_data://{q_exchange.value}/{symbol}/{interval.value}"
        )

        return BarFrame(
            df=df,
            provider="quant_data",
            symbol=symbol.upper(),
            level=level,
            exchange=exchange,
            calendar_version=cal_version,
            adjustment_mode="none",
            session_policy=session_policy,
            source_query=source_query,
            as_of=as_of,
            last_completed_ts=last_completed_ts,
            payload_hash=payload_hash,
        )

    def update(
        self,
        symbol: str,
        exchange: str,
        level: str,
        start: datetime,
        end: datetime | None = None,
        *,
        datafeed=None,
    ) -> int:
        """Fetch and store bars via the appropriate datafeed.

        Calls DataManager.update() with the right datafeed (PolygonDatafeed
        for NYSE/NASDAQ, MinishareDatafeed for CN exchanges).

        Args:
            symbol: ticker or contract code.
            exchange: MIC string (e.g. "XNYS", "XSHF").
            level: macd-momentum level string (e.g. "D", "60min").
            start: earliest date to fetch (UTC-aware or naive).
            end: latest date to fetch (default: now UTC).
            datafeed: explicit datafeed instance to use (overrides auto-select).

        Returns:
            Number of new bars written to storage.
        """
        from quant_data import DataManager

        q_exchange = self._map_exchange(exchange)
        interval = self._map_level(level)
        if datafeed is None:
            datafeed = _make_datafeed(q_exchange)

        manager = DataManager(datafeed=datafeed, storage=self._storage)
        return manager.update(symbol, q_exchange, interval, start, end)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _map_exchange(exchange: str) -> QExchange:
        try:
            return _EXCHANGE_MAP[exchange]
        except KeyError:
            supported = sorted(_EXCHANGE_MAP.keys())
            raise KeyError(
                f"Exchange {exchange!r} not in BarStore exchange map. "
                f"Supported: {supported}"
            ) from None

    @staticmethod
    def _map_level(level: str) -> Interval:
        try:
            return _LEVEL_TO_INTERVAL[level]
        except KeyError:
            supported = sorted(_LEVEL_TO_INTERVAL.keys())
            raise KeyError(
                f"Level {level!r} not in BarStore level map. "
                f"Supported: {supported}"
            ) from None

    @staticmethod
    def _build_bar_df(
        df_raw: pd.DataFrame,
        symbol: str,
        exchange: str,
        level: str,
        interval: Interval,
    ) -> pd.DataFrame:
        """Convert a quant-data DataFrame to BarFrame's expected format.

        quant-data columns:
            datetime, open_price, high_price, low_price, close_price,
            volume, amount, open_interest

        BarFrame required:  timestamp (UTC tz-aware), open, high, low, close
        BarFrame optional:  volume, open_interest
        """
        df = df_raw.copy()

        # Ensure datetime is tz-aware UTC
        if not pd.api.types.is_datetime64_any_dtype(df["datetime"]):
            df["datetime"] = pd.to_datetime(df["datetime"])
        if df["datetime"].dt.tz is None:
            df["datetime"] = df["datetime"].dt.tz_localize("UTC")
        else:
            df["datetime"] = df["datetime"].dt.tz_convert("UTC")

        # For US daily bars: map stored datetime → XNYS/XNAQ session_close
        # so the timestamp is the canonical period_end from exchange_calendars,
        # matching the alphavantage/polygon loaders.
        q_exchange_name = _EXCHANGE_MAP.get(exchange)
        if (
            q_exchange_name in _US_EXCHANGES
            and interval == Interval.DAILY
        ):
            # The stored datetime is the bar date at market close in UTC.
            # Re-derive via calendars.session_close to be consistent with
            # the alphavantage loader.
            mic = exchange  # e.g. "XNYS"
            timestamps: list[pd.Timestamp | None] = []
            import exchange_calendars as _ecals
            cal = _ecals.get_calendar(mic)
            cal_lower = cal.first_session.date()
            cal_upper = cal.last_session.date()
            for dt in df["datetime"]:
                date_obj = pd.Timestamp(dt).date()
                try:
                    if not calendars.is_session(mic, date_obj):
                        # Non-session date stored (e.g. weekend/holiday) —
                        # drop it (same as alphavantage loader).
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

            df["datetime"] = timestamps
            df = df[df["datetime"].notna()].copy()
            if df.empty:
                raise ValueError(
                    f"All bars for {symbol}/{exchange}/{level} were dropped "
                    f"during calendar session_close mapping (all OOB or "
                    f"non-session dates)."
                )
            df["datetime"] = pd.DatetimeIndex(df["datetime"]).tz_convert("UTC")

        # Column rename: quant-data → BarFrame
        df = df.rename(columns={
            "datetime":    "timestamp",
            "open_price":  "open",
            "high_price":  "high",
            "low_price":   "low",
            "close_price": "close",
        })

        # Keep only BarFrame-allowed columns (drop amount, etc.)
        keep = ["timestamp", "open", "high", "low", "close", "volume", "open_interest"]
        df = df[[c for c in keep if c in df.columns]]

        # Ensure numeric price columns
        for col in ("open", "high", "low", "close"):
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # Drop any rows where price data is NaN after coercion
        price_cols = ["open", "high", "low", "close"]
        df = df.dropna(subset=price_cols).reset_index(drop=True)

        if df.empty:
            raise ValueError(
                f"No valid price rows remain for {symbol}/{exchange}/{level} "
                f"after cleaning."
            )

        # Sort and dedup by timestamp
        df = df.sort_values("timestamp").drop_duplicates(
            subset=["timestamp"], keep="last"
        ).reset_index(drop=True)

        return df

    @staticmethod
    def _calendar_version(exchange: str, level: str) -> str:
        """Build a calendar_version string consistent with existing loaders.

        For US exchanges (XNYS/XNAQ): delegate to calendars.calendar_version_for
        since we use exchange_calendars for period_end stamping.
        For CN exchanges: synthetic version string (quant-data doesn't use
        exchange_calendars internally).
        """
        q_exchange = _EXCHANGE_MAP.get(exchange)
        if q_exchange in _US_EXCHANGES:
            # Use the same MIC the calendars module expects
            mic = exchange  # "XNYS" or "XNAQ"
            try:
                return str(calendars.calendar_version_for(mic))
            except Exception:
                # XNAQ is not in calendars.SUPPORTED_EXCHANGES; fall back
                # to XNYS (NYSE and NASDAQ share the same session calendar)
                return str(calendars.calendar_version_for("XNYS"))
        else:
            # CN / other: synthetic string identifying the quant-data version
            try:
                import quant_data as _qd
                qd_version = _qd.__version__
            except AttributeError:
                qd_version = "unknown"
            return f"quant_data=={qd_version}+{exchange}"
