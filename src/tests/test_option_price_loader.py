import json
from datetime import date
from pathlib import Path

import pandas as pd
from engine.options.option_price_loader import load_option_daily


def _write_contract(dir_: Path, sym: str, rows):
    bars = []
    for d, o, h, l, c in rows:
        ts = int(pd.Timestamp(d, tz="UTC").timestamp())
        bars.append({"time": ts, "open": o, "high": h, "low": l, "close": c, "volume": 1})
    (dir_ / f"{sym}_daily.json").write_text(json.dumps({"contract": sym, "bars": bars}))


def test_load_option_daily_returns_ohlc_from_entry(tmp_path):
    _write_contract(tmp_path, "ag2510c9000",
                    [("2025-09-01", 10, 11, 9, 10),
                     ("2025-09-02", 10, 20, 10, 18),
                     ("2025-09-03", 18, 19, 17, 17)])
    df = load_option_daily("ag2510c9000", date(2025, 9, 1), tmp_path, max_hold=30)
    assert list(df.columns) >= ["open", "high", "low", "close"]
    assert len(df) == 3
    assert float(df["close"].iloc[0]) == 10.0


def test_load_option_daily_missing_returns_none(tmp_path):
    assert load_option_daily("ag9999c1", date(2025, 1, 1), tmp_path, max_hold=30) is None


from engine.options.option_price_loader import model_option_daily


def _ul(prices):
    idx = pd.date_range("2025-09-01", periods=len(prices), freq="D", tz="UTC")
    return pd.DataFrame({"timestamp": idx, "open": prices, "high": prices,
                         "low": prices, "close": prices, "volume": [1] * len(prices)})


def test_model_option_daily_prices_with_black76():
    ul = _ul([9000, 9100, 9300, 9200])  # underlying rises -> call gains
    df = model_option_daily(strike=9000, expiry=date(2025, 12, 17),
                            entry_date=date(2025, 9, 1), underlying=ul,
                            iv=0.18, max_hold=30)
    assert len(df) == 4
    assert float(df["close"].iloc[2]) > float(df["close"].iloc[0])
    assert float(df["high"].iloc[0]) >= float(df["close"].iloc[0])


def test_model_option_daily_truncates_at_expiry():
    # 40-day underlying path but the option expires on day 10 -> the modeled
    # path must stop at expiry (no post-expiry pricing rows).
    ul = _ul([9000] * 40)  # 2025-09-01 .. 2025-10-10
    df = model_option_daily(strike=9000, expiry=date(2025, 9, 10),
                            entry_date=date(2025, 9, 1), underlying=ul,
                            iv=0.18, max_hold=30)
    assert len(df) == 10  # 2025-09-01 .. 2025-09-10 inclusive


from engine.options.option_price_loader import premium_path


def test_premium_path_prefers_market(tmp_path):
    _write_contract(tmp_path, "ag2510c9000",
                    [(f"2025-09-0{i}", 10, 11, 9, 10) for i in range(1, 8)])
    ul = _ul([9000] * 7)
    df, src = premium_path("ag2510c9000", strike=9000, expiry=date(2025, 12, 17),
                           entry_date=date(2025, 9, 1), data_dir=tmp_path,
                           underlying=ul, iv=0.18, max_hold=30, min_cover=5)
    assert src == "market" and len(df) >= 5


def test_premium_path_falls_back_to_model(tmp_path):
    ul = _ul([9000, 9100, 9300, 9200, 9200, 9200])
    df, src = premium_path("ag9999c9000", strike=9000, expiry=date(2025, 12, 17),
                           entry_date=date(2025, 9, 1), data_dir=tmp_path,
                           underlying=ul, iv=0.18, max_hold=30, min_cover=5)
    assert src == "model" and df is not None


from engine.options.black76 import black76_price


def test_model_option_daily_matches_black76():
    """Regression: model_option_daily must produce prices consistent
    with black76_price() — verify fixed F/K/T/r/sigma match exactly."""
    ul = _ul([6000, 6100, 6200])
    strike = 6100.0
    expiry = date(2025, 9, 10)
    entry = date(2025, 9, 1)  # aligns with _ul date_range start
    r = 0.02
    iv = 0.13
    df = model_option_daily(strike=strike, expiry=expiry, entry_date=entry,
                            underlying=ul, iv=iv, max_hold=30, r=r)
    assert df is not None and len(df) == 3
    # Each OHLC field must equal black76_price(F, K, T, r, iv, "C")
    for i, (_, b) in enumerate(ul.iterrows()):
        T = max((expiry - entry).days - i, 0) / 365.0
        expected = black76_price(float(b["close"]), strike, T, r, iv, "C")
        assert abs(float(df["close"].iloc[i]) - expected) < 1e-6, \
            f"row {i}: model {df['close'].iloc[i]:.6f} != black76 {expected:.6f} (T={T:.4f})"
    # Spot-check the review's F=6000, K=6100, T=9/365, sigma=13% case (day 0)
    T0 = 9.0 / 365.0
    b76 = black76_price(6000.0, 6100.0, T0, 0.02, 0.13, "C")
    assert abs(float(df["close"].iloc[0]) - b76) < 1e-6
