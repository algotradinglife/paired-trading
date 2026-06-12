"""OptionStore — unified read seam for CN option contracts in the
quant-cli Parquet store (the options counterpart of data/store.py).

Layout: one file per option contract under ``{root}/daily/``, standard
8-column schema, naive Beijing datetimes (date markers at daily level).
Four filename dialects (see strategy-data-access-guide.md §4):

    SHFE/INE : ``SHFE.ag2607C19900``
    DCE      : ``DCE.i2607-C-740``
    CZCE     : ``CZCE.CF509C13000``  (3-digit month -> 2020s decade)
    US OCC   : ``O:SPY240621C00495000.AMEX``  (strike in 1/1000 dollars)

CN contracts are exposed under the normalized lowercase symbol
``{prod}{yymm}{c|p}{strike}`` (e.g. ``ag2607c19900``) — the same
convention ``cn_{ag,au}_selector`` emits in score_today records.
US contracts use ``{und}{yymmdd}{c|p}{strike}`` (e.g. ``spy240621c495``)
with the product being the uppercase underlying ticker (``SPY``).

US contracts may have a ``*.greeks.parquet`` sibling (iv/delta/gamma/
theta/vega/rho/underlying_close, computed pipeline-side); read it via
``load_contract_greeks``. Greeks siblings are never contracts themselves.

Intraday option bars / bid-ask are NOT in the store yet (recorded in
doc/data_gaps_for_pipeline_2026-06-11.md); this seam is daily-only
until the pipeline backfills.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

_PRODUCT_TO_EXCHANGE: dict[str, str] = {
    "cu": "SHFE", "al": "SHFE", "au": "SHFE", "ag": "SHFE",
    "ni": "SHFE", "rb": "SHFE",
    "i": "DCE", "m": "DCE", "y": "DCE", "j": "DCE",
    "CF": "CZCE", "RM": "CZCE", "SR": "CZCE",
    "sc": "INE",
}

# filename dialects → (product, month_digits, C/P, strike)
_SHFE_INE_RE = re.compile(r"(?:SHFE|INE)\.([a-z]+)(\d{4})([CP])(\d+)")
_DCE_RE = re.compile(r"DCE\.([a-z]+)(\d{4})-([CP])-(\d+)")
_CZCE_RE = re.compile(r"CZCE\.([A-Z]+)(\d{3,4})([CP])(\d+)")
# US OCC: O:{UND}{YYMMDD}{C|P}{strike*1000:08d}.{exchange}
_US_OCC_RE = re.compile(
    r"O:([A-Z]+)(\d{6})([CP])(\d{8})\.(?:AMEX|NYSE|NASDAQ|ARCA)"
)


def _canonical_yymm(digits: str) -> str:
    """'2509' stays; 3-digit '509' -> '2509' (2020s decade)."""
    return digits if len(digits) == 4 else f"2{digits}"


@dataclass(frozen=True)
class OptionContract:
    contract_sym: str       # normalized, e.g. "ag2607c19900" / "spy240621c495"
    product: str            # store-case product code ("ag", "CF", "SPY")
    underlying_month: str   # YYMM, e.g. "2607"
    opt_type: str           # "C" | "P"
    strike: float
    path: Path
    expiry: date | None = None   # exact expiry (US OCC only; CN unknown)


_STORE_CACHE: dict[str, "OptionStore"] = {}


def get_store(data_root: Path | str) -> "OptionStore":
    """Process-wide OptionStore per root (the catalog glob over /mnt is
    slow enough to be worth sharing)."""
    key = str(data_root)
    store = _STORE_CACHE.get(key)
    if store is None:
        store = OptionStore(data_root)
        _STORE_CACHE[key] = store
    return store


class OptionStore:
    """Read-only catalog + bar access for CN option contracts."""

    def __init__(self, data_root: Path | str) -> None:
        self._root = Path(data_root)
        self._catalog_cache: dict[str, list[OptionContract]] = {}
        self._coverage_cache: dict[str, dict[str, tuple[date, date]]] = {}
        self._sym_index: dict[str, OptionContract] | None = None

    # ------------------------------------------------------------------
    # Catalog
    # ------------------------------------------------------------------

    def catalog(self, product: str) -> list[OptionContract]:
        """All option contracts for a product (store-case code)."""
        cached = self._catalog_cache.get(product)
        if cached is not None:
            return cached

        daily = self._root / "daily"
        out: list[OptionContract] = []
        if daily.is_dir():
            for p in daily.glob("*.parquet"):
                c = self._parse(p)
                if c is not None and c.product == product:
                    out.append(c)
        out.sort(key=lambda c: (c.underlying_month, c.opt_type, c.strike))
        self._catalog_cache[product] = out
        return out

    @staticmethod
    def _parse(path: Path) -> OptionContract | None:
        stem = path.stem
        if stem.endswith(".greeks"):
            return None
        m = _US_OCC_RE.fullmatch(stem)
        if m:
            und, yymmdd, cp, strike_milli = m.groups()
            strike = int(strike_milli) / 1000.0
            expiry = date(
                2000 + int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6])
            )
            return OptionContract(
                contract_sym=f"{und.lower()}{yymmdd}{cp.lower()}{strike:g}",
                product=und,
                underlying_month=yymmdd[:4],
                opt_type=cp,
                strike=strike,
                path=path,
                expiry=expiry,
            )
        for rx in (_SHFE_INE_RE, _DCE_RE, _CZCE_RE):
            m = rx.fullmatch(stem)
            if m:
                prod, digits, cp, strike = m.groups()
                yymm = _canonical_yymm(digits)
                return OptionContract(
                    contract_sym=f"{prod.lower()}{yymm}{cp.lower()}{int(strike)}",
                    product=prod,
                    underlying_month=yymm,
                    opt_type=cp,
                    strike=float(strike),
                    path=path,
                )
        return None

    def _lookup(self, contract_sym: str) -> OptionContract | None:
        if self._sym_index is None:
            daily = self._root / "daily"
            idx: dict[str, OptionContract] = {}
            if daily.is_dir():
                for p in daily.glob("*.parquet"):
                    c = self._parse(p)
                    if c is not None:
                        idx[c.contract_sym] = c
            self._sym_index = idx
        return self._sym_index.get(contract_sym.lower())

    # ------------------------------------------------------------------
    # Bars
    # ------------------------------------------------------------------

    def load_contract_daily(self, contract_sym: str) -> pd.DataFrame | None:
        """Full daily history for one contract, with a ``date`` column."""
        c = self._lookup(contract_sym)
        if c is None:
            return None
        df = pd.read_parquet(c.path)
        if df.empty:
            return None
        df = df.copy()
        df["date"] = pd.to_datetime(df["datetime"]).dt.date
        return (
            df.sort_values("date")
            .drop_duplicates(subset=["date"], keep="last")
            .reset_index(drop=True)
        )

    def load_contract_greeks(self, contract_sym: str) -> pd.DataFrame | None:
        """Greeks sibling history (iv/delta/gamma/theta/vega/rho/
        underlying_close) with a ``date`` column; None when the contract
        is unknown or has no ``*.greeks.parquet`` file."""
        c = self._lookup(contract_sym)
        if c is None:
            return None
        gp = c.path.with_name(f"{c.path.stem}.greeks.parquet")
        if not gp.exists():
            return None
        df = pd.read_parquet(gp)
        if df.empty:
            return None
        df = df.copy()
        df["date"] = pd.to_datetime(df["datetime"]).dt.date
        return (
            df.sort_values("date")
            .drop_duplicates(subset=["date"], keep="last")
            .reset_index(drop=True)
        )

    def coverage(self, product: str) -> dict[str, tuple[date, date]]:
        """contract_sym → (first bar date, last bar date), cached per product."""
        cached = self._coverage_cache.get(product)
        if cached is not None:
            return cached
        cov: dict[str, tuple[date, date]] = {}
        for c in self.catalog(product):
            df = self.load_contract_daily(c.contract_sym)
            if df is None or df.empty:
                continue
            cov[c.contract_sym] = (df["date"].iloc[0], df["date"].iloc[-1])
        self._coverage_cache[product] = cov
        return cov

    def load_chain(self, product: str, on: date) -> pd.DataFrame:
        """All contracts of ``product`` with a bar on ``on``.

        Columns: contract_sym, underlying_month, opt_type, strike + the
        bar's OHLCV/turnover/open_interest for that date.
        """
        rows = []
        for c in self.catalog(product):
            df = self.load_contract_daily(c.contract_sym)
            if df is None:
                continue
            hit = df[df["date"] == on]
            if hit.empty:
                continue
            b = hit.iloc[-1]
            rows.append({
                "contract_sym": c.contract_sym,
                "underlying_month": c.underlying_month,
                "opt_type": c.opt_type,
                "strike": c.strike,
                "open": b["open"], "high": b["high"], "low": b["low"],
                "close": b["close"], "volume": b["volume"],
                "turnover": b["turnover"], "open_interest": b["open_interest"],
            })
        return pd.DataFrame(
            rows,
            columns=[
                "contract_sym", "underlying_month", "opt_type", "strike",
                "open", "high", "low", "close", "volume", "turnover",
                "open_interest",
            ],
        )

    def close_on(
        self, contract_sym: str, on: date, *, max_lag_days: int = 5
    ) -> float | None:
        """Contract close at ``on``, or the nearest earlier session within
        ``max_lag_days``; None when no bar qualifies."""
        df = self.load_contract_daily(contract_sym)
        if df is None:
            return None
        eligible = df[
            (df["date"] <= on) & (df["date"] >= on - timedelta(days=max_lag_days))
        ]
        if eligible.empty:
            return None
        return float(eligible["close"].iloc[-1])
