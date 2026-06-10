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
