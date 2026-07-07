"""OptionStore (CN options parquet seam) + Black-76 inversion.

Store layout under test: daily/{FILE}.parquet with the standard 8-col
schema, one file per option contract, three filename dialects:

    SHFE/INE : SHFE.ag2607C19900
    DCE      : DCE.i2607-C-740
    CZCE     : CZCE.CF509C13000   (3-digit month -> 2020s decade)

Normalized contract_sym is lowercase "{prod}{yymm}{c|p}{strike}"
(matches the cn_{ag,au}_selector convention, e.g. "ag2607c19900").
"""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest

from data.option_store import OptionStore
from engine.options.black76 import black76_price, implied_vol


def _bar(dt: datetime, close: float, vol: float = 10.0) -> dict:
    return {
        "datetime": dt, "open": close, "high": close + 1, "low": max(close - 1, 0.1),
        "close": close, "volume": vol, "turnover": close * vol, "open_interest": 5.0,
    }


def _write(root, name, bars):
    d = root / "daily"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(bars).to_parquet(d / f"{name}.parquet", index=False)


# ---------------------------------------------------------------------------
# Catalog / filename dialects
# ---------------------------------------------------------------------------

def test_catalog_parses_three_dialects(tmp_path):
    _write(tmp_path, "SHFE.ag2607C19900", [_bar(datetime(2026, 5, 4), 250)])
    _write(tmp_path, "DCE.i2607-P-740", [_bar(datetime(2026, 5, 4), 30)])
    _write(tmp_path, "CZCE.CF509C13000", [_bar(datetime(2025, 3, 4), 200)])
    store = OptionStore(tmp_path)

    ag = store.catalog("ag")
    assert len(ag) == 1
    assert ag[0].contract_sym == "ag2607c19900"
    assert (ag[0].opt_type, ag[0].strike, ag[0].underlying_month) == ("C", 19900.0, "2607")

    i = store.catalog("i")
    assert i[0].contract_sym == "i2607p740"
    assert i[0].opt_type == "P"

    cf = store.catalog("CF")
    assert cf[0].contract_sym == "cf2509c13000"
    assert cf[0].underlying_month == "2509"


def test_catalog_ignores_futures_and_other_products(tmp_path):
    _write(tmp_path, "SHFE.ag2607", [_bar(datetime(2026, 5, 4), 24000)])      # future
    _write(tmp_path, "SHFE.au2608C780", [_bar(datetime(2026, 5, 4), 12)])     # other product
    store = OptionStore(tmp_path)
    assert store.catalog("ag") == []


# ---------------------------------------------------------------------------
# Chain / contract access
# ---------------------------------------------------------------------------

def test_load_chain_returns_contracts_with_bars_on_date(tmp_path):
    _write(tmp_path, "SHFE.ag2607C19900", [_bar(datetime(2026, 5, 4), 250)])
    _write(tmp_path, "SHFE.ag2607P19900", [_bar(datetime(2026, 5, 4), 180)])
    _write(tmp_path, "SHFE.ag2607C20100", [_bar(datetime(2026, 5, 6), 150)])  # not on 5-4
    chain = OptionStore(tmp_path).load_chain("ag", date(2026, 5, 4))
    assert set(chain["contract_sym"]) == {"ag2607c19900", "ag2607p19900"}
    row = chain[chain["contract_sym"] == "ag2607c19900"].iloc[0]
    assert row["close"] == 250 and row["opt_type"] == "C" and row["strike"] == 19900.0


def test_close_on_nearest_within_lag(tmp_path):
    _write(tmp_path, "SHFE.ag2607C19900", [
        _bar(datetime(2026, 5, 4), 250),
        _bar(datetime(2026, 5, 8), 260),
    ])
    store = OptionStore(tmp_path)
    assert store.close_on("ag2607c19900", date(2026, 5, 4)) == 250
    assert store.close_on("ag2607c19900", date(2026, 5, 6)) == 250   # nearest <=
    assert store.close_on("ag2607c19900", date(2026, 5, 20), max_lag_days=5) is None
    assert store.close_on("ag9999c1", date(2026, 5, 4)) is None      # unknown contract


def test_load_contract_daily_full_history(tmp_path):
    _write(tmp_path, "SHFE.ag2607C19900", [
        _bar(datetime(2026, 5, 4), 250), _bar(datetime(2026, 5, 5), 255),
    ])
    df = OptionStore(tmp_path).load_contract_daily("ag2607c19900")
    assert list(df["close"]) == [250, 255]
    assert df["date"].iloc[0] == date(2026, 5, 4)


# ---------------------------------------------------------------------------
# Black-76
# ---------------------------------------------------------------------------

def test_black76_implied_vol_round_trip_call_and_put():
    F, K, T, r = 24000.0, 25000.0, 45 / 365.0, 0.02
    for opt_type, sigma in (("C", 0.22), ("P", 0.35)):
        px = black76_price(F, K, T, r, sigma, opt_type)
        iv = implied_vol(px, F, K, T, r, opt_type)
        assert iv == pytest.approx(sigma, abs=1e-4)


def test_black76_put_call_parity():
    F, K, T, r, sigma = 24000.0, 24000.0, 30 / 365.0, 0.02, 0.2
    import math
    c = black76_price(F, K, T, r, sigma, "C")
    p = black76_price(F, K, T, r, sigma, "P")
    assert c - p == pytest.approx(math.exp(-r * T) * (F - K), abs=1e-6)


def test_implied_vol_none_below_intrinsic():
    # deep ITM call priced below discounted intrinsic — unsolvable
    assert implied_vol(500.0, 24000.0, 23000.0, 30 / 365.0, 0.02, "C") is None


# ---------------------------------------------------------------------------
# enrich_with_iv store wiring (ag selector; au mirrors it)
# ---------------------------------------------------------------------------

def test_enrich_with_iv_uses_store_prices(tmp_path):
    from engine.options.cn_ag_selector import enrich_with_iv
    _write(tmp_path, "SHFE.ag2607C19900", [_bar(datetime(2026, 5, 4), 250)])
    calls = [{
        "contract_sym": "ag2607c19900", "strike": 19900,
        "days_to_expiry": 45, "otm_pct": 2.0, "expiry_month": "2607",
    }]
    # signal_date far in the past => live path skipped; empty JSON dir
    enrich_with_iv(
        calls, date(2026, 5, 4), 19500.0, tmp_path / "no_json",
        quant_root=tmp_path,
    )
    c = calls[0]
    assert c["option_price"] == 250
    assert c["price_source"] == "store"
    assert c["iv"] is not None and 0 < c["iv"] < 100


def test_load_option_daily_prefers_longer_source(tmp_path):
    # Mid-backfill: a 1-row parquet stub must not shadow a legacy JSON
    # file that actually covers the path (mirrors the BarStore
    # continuous-file rule).
    import json as _json
    from engine.options.option_price_loader import load_option_daily
    _write(tmp_path, "SHFE.ag2607C19900", [_bar(datetime(2026, 5, 5), 255)])
    json_dir = tmp_path / "json"
    json_dir.mkdir()

    def epoch(d):
        return int(pd.Timestamp(d, tz="UTC").timestamp())

    bars = [
        {"time": epoch("2026-05-05"), "open": 250, "high": 256, "low": 249, "close": 255},
        {"time": epoch("2026-05-06"), "open": 255, "high": 261, "low": 254, "close": 260},
        {"time": epoch("2026-05-07"), "open": 260, "high": 266, "low": 259, "close": 265},
    ]
    (json_dir / "ag2607c19900_daily.json").write_text(_json.dumps({"bars": bars}))
    df = load_option_daily(
        "ag2607c19900", date(2026, 5, 5), json_dir,
        max_hold=30, quant_root=tmp_path,
    )
    assert list(df["close"]) == [255, 260, 265]   # JSON (3 rows) beats stub (1)


def test_load_option_daily_rejects_late_listed_source(tmp_path):
    # codex P2: a contract whose data STARTS after the signal was not
    # tradable then — its bars must not be served as market data (the
    # entry would silently shift to the listing date)
    from engine.options.option_price_loader import load_option_daily
    _write(tmp_path, "SHFE.ag2607C19900", [
        _bar(datetime(2026, 5, 20), 250), _bar(datetime(2026, 5, 21), 255),
        _bar(datetime(2026, 5, 22), 260), _bar(datetime(2026, 5, 25), 250),
        _bar(datetime(2026, 5, 26), 255),
    ])
    df = load_option_daily(
        "ag2607c19900", date(2026, 5, 4), tmp_path / "no_json",
        max_hold=30, quant_root=tmp_path,
        require_listed_by=date(2026, 5, 4),
    )
    assert df is None
    # listed before the signal -> served normally
    df2 = load_option_daily(
        "ag2607c19900", date(2026, 5, 21), tmp_path / "no_json",
        max_hold=30, quant_root=tmp_path,
        require_listed_by=date(2026, 5, 21),
    )
    assert df2 is not None and list(df2["close"])[:2] == [255, 260]


def test_load_option_daily_parquet_first(tmp_path):
    from engine.options.option_price_loader import load_option_daily
    _write(tmp_path, "SHFE.ag2607C19900", [
        _bar(datetime(2026, 5, 4), 250), _bar(datetime(2026, 5, 5), 255),
        _bar(datetime(2026, 5, 6), 260),
    ])
    df = load_option_daily(
        "ag2607c19900", date(2026, 5, 5), tmp_path / "no_json",
        max_hold=30, quant_root=tmp_path,
    )
    assert df is not None
    assert list(df["close"]) == [255, 260]   # from entry_date forward


# ---------------------------------------------------------------------------
# US OCC dialect (t_e7fb18c9): O:SPY240621C00495000.AMEX + greeks siblings
# ---------------------------------------------------------------------------

def _write_greeks(root, name, rows):
    d = root / "daily"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(d / f"{name}.greeks.parquet", index=False)


def _greek_row(dt: datetime, iv: float, underlying_close: float) -> dict:
    return {
        "datetime": dt, "iv": iv, "delta": 0.5, "gamma": 0.01,
        "theta": -0.2, "vega": 0.15, "rho": 0.1,
        "underlying_close": underlying_close,
    }


def test_catalog_parses_us_occ_dialect(tmp_path):
    _write(tmp_path, "O:SPY240621C00495000.AMEX", [_bar(datetime(2024, 6, 7), 41.1)])
    _write_greeks(tmp_path, "O:SPY240621C00495000.AMEX",
                  [_greek_row(datetime(2024, 6, 7), 0.31, 534.0)])
    store = OptionStore(tmp_path)
    spy = store.catalog("SPY")
    assert len(spy) == 1                      # greeks 伴生文件不是独立合约
    c = spy[0]
    assert c.opt_type == "C"
    assert c.strike == 495.0                  # 00495000 -> 495.0
    assert c.underlying_month == "2406"
    assert c.expiry == date(2024, 6, 21)      # OCC 文件名中的精确到期日


def test_us_occ_fractional_strike_and_put(tmp_path):
    _write(tmp_path, "O:GDX250620P00030500.AMEX", [_bar(datetime(2025, 5, 5), 1.2)])
    store = OptionStore(tmp_path)
    gdx = store.catalog("GDX")
    assert len(gdx) == 1
    assert gdx[0].opt_type == "P"
    assert gdx[0].strike == 30.5


def test_cn_contract_expiry_is_none(tmp_path):
    _write(tmp_path, "SHFE.ag2607C19900", [_bar(datetime(2026, 5, 4), 250)])
    store = OptionStore(tmp_path)
    assert store.catalog("ag")[0].expiry is None


def test_us_chain_coverage_close_on(tmp_path):
    _write(tmp_path, "O:SPY240621C00495000.AMEX", [
        _bar(datetime(2024, 6, 7), 41.1), _bar(datetime(2024, 6, 10), 41.07),
    ])
    _write(tmp_path, "O:SPY240621P00495000.AMEX", [_bar(datetime(2024, 6, 7), 2.5)])
    _write(tmp_path, "O:SPY240719C00500000.AMEX", [_bar(datetime(2024, 6, 10), 12.0)])
    store = OptionStore(tmp_path)

    chain = store.load_chain("SPY", date(2024, 6, 7))
    assert len(chain) == 2
    assert set(chain["opt_type"]) == {"C", "P"}

    cov = store.coverage("SPY")
    syms = list(cov)
    assert len(cov) == 3
    call_sym = store.catalog("SPY")[0].contract_sym
    assert cov[call_sym] == (date(2024, 6, 7), date(2024, 6, 10))

    assert store.close_on(call_sym, date(2024, 6, 10)) == 41.07
    assert store.close_on(call_sym, date(2024, 6, 12)) == 41.07  # lag fallback


def test_load_contract_daily_skips_greeks_only_symbol(tmp_path):
    # greeks 文件单独存在（无 bars 主文件）时不得出现在 catalog
    _write_greeks(tmp_path, "O:SPY240621C00400000.AMEX",
                  [_greek_row(datetime(2024, 6, 7), 0.3, 534.0)])
    store = OptionStore(tmp_path)
    assert store.catalog("SPY") == []


def test_load_contract_greeks(tmp_path):
    _write(tmp_path, "O:SPY240621C00495000.AMEX", [_bar(datetime(2024, 6, 7), 41.1)])
    _write_greeks(tmp_path, "O:SPY240621C00495000.AMEX", [
        _greek_row(datetime(2024, 6, 7), 0.31, 534.0),
        _greek_row(datetime(2024, 6, 10), 0.29, 536.2),
    ])
    _write(tmp_path, "O:QQQ240621C00480000.AMEX", [_bar(datetime(2024, 6, 7), 10.0)])
    store = OptionStore(tmp_path)

    sym = store.catalog("SPY")[0].contract_sym
    g = store.load_contract_greeks(sym)
    assert g is not None and len(g) == 2
    assert {"iv", "delta", "gamma", "theta", "vega", "rho",
            "underlying_close", "date"} <= set(g.columns)
    assert g["date"].iloc[0] == date(2024, 6, 7)
    assert g["iv"].iloc[1] == pytest.approx(0.29)

    # QQQ 无 greeks 伴生文件 -> None
    qqq_sym = store.catalog("QQQ")[0].contract_sym
    assert store.load_contract_greeks(qqq_sym) is None
    # 未知合约 -> None
    assert store.load_contract_greeks("nonexistent") is None
