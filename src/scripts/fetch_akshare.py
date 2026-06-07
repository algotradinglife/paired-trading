"""AKShare 数据抓取：国内股指期货 + 商品期货 + 对应期权 + QVIX。

补 Polygon/Qveris 的国内市场空缺。所有输出转 Polygon-style JSON shape
(time/open/high/low/close/volume) 落到 data/raw/，与 engine 现有 loader 兼容。

支持的资产类别：
  - 股指期货主力连续（CFFEX）：IF0/IH0/IC0/IM0/TS0/TF0/T0/TL0
  - 商品期货主力连续：rb0/cu0/au0/m0/i0/sc0/TA0/MA0 等
  - 股指/ETF 期权：CFFEX HS300/SZ50/ZZ1000 + 上证 ETF 期权
  - 商品期权（具体合约，如 m2509C2900）
  - QVIX 隐含波动率指数（300ETF/50ETF/etc）

Usage:
  uv run python scripts/fetch_akshare.py --futures IF0 IH0 IC0 IM0
  uv run python scripts/fetch_akshare.py --futures rb0 cu0 au0 m0 i0 sc0 TA0 MA0
  uv run python scripts/fetch_akshare.py --qvix 300etf 50etf
  uv run python scripts/fetch_akshare.py --option-comm m2509C2900 m2509P2900
  uv run python scripts/fetch_akshare.py --option-cffex io2606C4300 io2606P4300
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import akshare as ak
import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
SLEEP_BETWEEN = 0.5
# Chinese market close ≈ 15:00 CST = 07:00 UTC; we stamp daily bars at 07:00 UTC
DAILY_STAMP_UTC_HOUR = 7


def _sanitize(sym: str) -> str:
    """Convert ticker into safe filename stem."""
    return sym.lower().replace(":", "_").replace(".", "_")


def _to_unix_seconds(date_value, hour: int = DAILY_STAMP_UTC_HOUR) -> int:
    """Convert a date / datetime / pandas timestamp to unix seconds at given UTC hour."""
    if isinstance(date_value, str):
        try:
            ts = pd.to_datetime(date_value)
        except Exception:
            raise
    elif isinstance(date_value, pd.Timestamp):
        ts = date_value
    elif isinstance(date_value, (datetime,)):
        ts = pd.Timestamp(date_value)
    else:
        ts = pd.Timestamp(date_value)
    # treat as naive date → UTC at given hour
    dt = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
    if getattr(dt, "tzinfo", None) is not None:
        dt = dt.replace(tzinfo=None)
    return int(datetime(dt.year, dt.month, dt.day, hour, 0, tzinfo=timezone.utc).timestamp())


def _df_to_bars(df: pd.DataFrame, date_col: str = "date") -> list[dict]:
    """Normalize an akshare daily DataFrame into Polygon-style bar dicts."""
    if df is None or df.empty:
        return []
    bars: list[dict] = []
    # Normalize column names — sina-style returns lowercase; some endpoints return Chinese
    cn_to_en = {
        "日期": "date", "时间": "date",
        "开盘价": "open", "开盘": "open",
        "最高价": "high", "最高": "high",
        "最低价": "low",  "最低": "low",
        "收盘价": "close", "收盘": "close",
        "成交量": "volume", "持仓量": "hold",
    }
    df = df.rename(columns={c: cn_to_en[c] for c in df.columns if c in cn_to_en})
    if date_col not in df.columns:
        raise ValueError(f"missing date column '{date_col}'; have {list(df.columns)}")

    for _, row in df.iterrows():
        try:
            t = _to_unix_seconds(row[date_col])
            bars.append({
                "time": t,
                "open":   float(row.get("open",  0) or 0),
                "high":   float(row.get("high",  0) or 0),
                "low":    float(row.get("low",   0) or 0),
                "close":  float(row.get("close", 0) or 0),
                "volume": int(float(row.get("volume", 0) or 0)),
            })
        except Exception as e:
            print(f"  skip row {row.to_dict()}: {e}", file=sys.stderr)
    bars.sort(key=lambda b: b["time"])
    # dedupe by time
    seen = set()
    out = []
    for b in bars:
        if b["time"] in seen:
            continue
        seen.add(b["time"])
        out.append(b)
    return out


def write_snapshot(symbol: str, resolution: str, source: str, bars: list[dict]) -> Path:
    payload = {
        "symbol": symbol,
        "resolution": resolution,
        "source": source,
        "fetched_at_data_ts": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "bars": bars,
    }
    name_suffix = "daily" if resolution == "1D" else resolution
    path = DATA_DIR / f"{_sanitize(symbol)}_{name_suffix}.json"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":")))
    return path


def fmt_range(bars: list[dict]) -> str:
    if not bars:
        return "(empty)"
    first = datetime.fromtimestamp(bars[0]["time"], tz=timezone.utc).strftime("%Y-%m-%d")
    last = datetime.fromtimestamp(bars[-1]["time"], tz=timezone.utc).strftime("%Y-%m-%d")
    return f"{first} → {last}"


# ---------------------------------------------------------------------------
# Asset-specific fetchers
# ---------------------------------------------------------------------------

def fetch_zh_futures_main(symbol: str) -> list[dict]:
    """股指 / 商品期货主力连续合约日线，如 'IF0' 'rb0' 'cu0' 'm0' ...
    使用 sina 数据。日期列名 'date'，OHLC 已为英文小写。
    """
    df = ak.futures_zh_daily_sina(symbol=symbol)
    return _df_to_bars(df, date_col="date")


def fetch_option_cffex_daily(symbol: str) -> list[dict]:
    """CFFEX 股指期权某一具体合约日线，如 'io2606C4300' / 'ho2603P2700' / 'mo2606C7000'。
    Symbol 前缀决定调用哪个函数：io=HS300, ho=SZ50, mo=ZZ1000。
    """
    lower = symbol.lower()
    if lower.startswith("io"):
        df = ak.option_cffex_hs300_daily_sina(symbol=lower)
    elif lower.startswith("ho"):
        df = ak.option_cffex_sz50_daily_sina(symbol=lower)
    elif lower.startswith("mo"):
        df = ak.option_cffex_zz1000_daily_sina(symbol=lower)
    else:
        raise ValueError(f"unrecognized CFFEX option symbol prefix: {symbol}")
    return _df_to_bars(df, date_col="date")


def fetch_option_commodity_sina(symbol: str) -> list[dict]:
    """商品期权某具体合约日线，如 'm2509C2900' / 'au2606C800' / 'i2509P700'。"""
    df = ak.option_commodity_hist_sina(symbol=symbol)
    return _df_to_bars(df, date_col="date")


def fetch_qvix(kind: str) -> list[dict]:
    """中国版 VIX。kind ∈ {300etf, 50etf, 500etf, 1000etf, 300index, 50index, 1000index,
    cyb (创业板 ETF), kcb (科创 50 ETF), 100etf}.
    """
    mapping = {
        "300etf":   ak.index_option_300etf_qvix,
        "50etf":    ak.index_option_50etf_qvix,
        "500etf":   ak.index_option_500etf_qvix,
        "1000etf":  ak.index_option_1000etf_qvix if hasattr(ak, "index_option_1000etf_qvix") else None,
        "300index": ak.index_option_300index_qvix,
        "50index":  ak.index_option_50index_qvix,
        "1000index": ak.index_option_1000index_qvix,
        "cyb":      ak.index_option_cyb_qvix,
        "kcb":      ak.index_option_kcb_qvix,
        "100etf":   ak.index_option_100etf_qvix,
    }
    fn = mapping.get(kind.lower())
    if fn is None:
        raise ValueError(f"unknown QVIX kind: {kind}. Available: {sorted(mapping)}")
    df = fn()
    return _df_to_bars(df, date_col="date")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--futures", nargs="*", default=[],
                        help="股指/商品期货主力连续，如 IF0 IH0 rb0 cu0 m0")
    parser.add_argument("--qvix", nargs="*", default=[],
                        help="QVIX 类型，如 300etf 50etf 1000index")
    parser.add_argument("--option-cffex", nargs="*", default=[],
                        help="CFFEX 股指期权具体合约，如 io2606C4300 ho2603P2700")
    parser.add_argument("--option-comm", nargs="*", default=[],
                        help="商品期权具体合约，如 m2509C2900 au2606P800")
    args = parser.parse_args()

    if not any([args.futures, args.qvix, args.option_cffex, args.option_comm]):
        parser.print_help()
        return 1

    for sym in args.futures:
        print(f"Fetching futures {sym}…")
        try:
            bars = fetch_zh_futures_main(sym)
        except Exception as e:
            print(f"  {sym}: ERROR — {e}", file=sys.stderr)
            continue
        if bars:
            p = write_snapshot(sym, "1D", "akshare-sina", bars)
            print(f"  {sym}: {len(bars)} bars {fmt_range(bars)} → {p.name}")
        else:
            print(f"  {sym}: empty")
        time.sleep(SLEEP_BETWEEN)

    for kind in args.qvix:
        print(f"Fetching QVIX {kind}…")
        try:
            bars = fetch_qvix(kind)
        except Exception as e:
            print(f"  qvix_{kind}: ERROR — {e}", file=sys.stderr)
            continue
        if bars:
            sym = f"qvix_{kind.lower()}"
            p = write_snapshot(sym, "1D", "akshare-qvix", bars)
            print(f"  {sym}: {len(bars)} bars {fmt_range(bars)} → {p.name}")
        time.sleep(SLEEP_BETWEEN)

    for sym in args.option_cffex:
        print(f"Fetching CFFEX option {sym}…")
        try:
            bars = fetch_option_cffex_daily(sym)
        except Exception as e:
            print(f"  {sym}: ERROR — {e}", file=sys.stderr)
            continue
        if bars:
            p = write_snapshot(sym, "1D", "akshare-sina-cffex-option", bars)
            print(f"  {sym}: {len(bars)} bars {fmt_range(bars)} → {p.name}")
        time.sleep(SLEEP_BETWEEN)

    for sym in args.option_comm:
        print(f"Fetching commodity option {sym}…")
        try:
            bars = fetch_option_commodity_sina(sym)
        except Exception as e:
            print(f"  {sym}: ERROR — {e}", file=sys.stderr)
            continue
        if bars:
            p = write_snapshot(sym, "1D", "akshare-sina-commodity-option", bars)
            print(f"  {sym}: {len(bars)} bars {fmt_range(bars)} → {p.name}")
        time.sleep(SLEEP_BETWEEN)

    return 0


if __name__ == "__main__":
    sys.exit(main())
