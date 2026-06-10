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
