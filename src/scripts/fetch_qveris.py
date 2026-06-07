"""Qveris CN futures intraday fetcher.

Replaces TqSdk for CN intraday backfill — TqSdk free tier caps at 10000 bars
per call (`get_kline_serial`) and the deeper API (`get_kline_data_series`)
is paid-only. Qveris's `ths_ifind.hf_basic_quotation.v1` has no row cap;
the qveris CLI truncates the printed response > 20480 bytes but the full
data is downloadable from `full_content_file_url`.

Output JSON format matches fetch_tqsdk.py / fetch_polygon.py so engine
code reads identically:
  {
    "symbol": "kq_m_shfe_au",          (filename-safe stem)
    "thscode": "AU00.SHF",             (original CN code)
    "resolution": "60",
    "source": "qveris",
    "fetched_at_data_ts": "2026-05-26",
    "bars": [{"time": <unix_utc>, "open": ..., "high": ..., "low": ..., "close": ..., "volume": ...}]
  }

Time conversion: qveris returns CN-local "YYYY-MM-DD HH:MM" (Asia/Shanghai
= UTC+8). We convert to UTC epoch seconds so engine pipeline is identical
to TqSdk output.

Cost note: billed by (bars × fields_per_bar) × 0.000858 + min 1 credit/call.
Single wide-range calls are most efficient (avoid min-charge floor).

Auth: QVERIS_API_KEY in env (loadable via scripts/_with_creds.sh qveris).
Uses qveris CLI as transport (already authenticated via ~/.qveris config).

Usage:
  scripts/_with_creds.sh qveris uv run python scripts/fetch_qveris.py \\
      AU00.SHF --tf 60min --start 2018-01-01 --end 2026-05-26
  scripts/_with_creds.sh qveris uv run python scripts/fetch_qveris.py \\
      AU00.SHF M00.DCE I00.DCE --tf 60min 15min --start 2020-01-01
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

TF_TO_QVERIS_INTERVAL = {
    "1min": "1",  "3min": "3",  "5min": "5",
    "10min": "10", "15min": "15", "30min": "30",
    "60min": "60",
}
TF_TO_SUFFIX = {  # filename suffix
    "1min": "1", "3min": "3", "5min": "5",
    "10min": "10", "15min": "15", "30min": "30",
    "60min": "60",
    "daily": "daily",
}

# CN futures local timezone
CN_TZ = timezone(timedelta(hours=8))


# Map THS exchange suffix → canonical (matches TqSdk fetch_tqsdk.py output naming).
# Without this mapping, qveris stems would not match the
# `kq_m_<exch>_<product>` files that analyze_sweet_spots_pool /
# backtest_cn_b_topology / score_today already consume.
QVERIS_EXCHANGE_MAP = {
    "SHF":  "shfe",
    "DCE":  "dce",
    "CFE":  "cffex",
    "INE":  "ine",
    "ZCE":  "czce",
    "CZC":  "czce",
    "GFEX": "gfex",
}


def _sanitize_thscode(thscode: str) -> str:
    """AU00.SHF → kq_m_shfe_au   (continuous main contract)
    RB2610.SHF → kq_m_shfe_rb2610 (specific expiry)

    Matches fetch_tqsdk.py stem convention so engine consumers
    (analyze_sweet_spots_pool, backtest_cn_b_topology, score_today, etc.)
    pick up qveris backfills as drop-in replacements (codex 2026-05-26).
    """
    m = re.match(r"^([A-Z]+)(\d*)\.([A-Z]+)$", thscode.upper())
    if not m:
        # Fallback for unrecognized format: simple sanitization
        s = re.sub(r"[^0-9a-zA-Z]+", "_", thscode.lower()).strip("_")
        return f"kq_m_{s}"
    product, expiry, exch = m.group(1), m.group(2), m.group(3)
    canonical_exch = QVERIS_EXCHANGE_MAP.get(exch, exch.lower())
    # Continuous-contract suffixes — strip so stem matches TqSdk's main-contract
    # naming. Anything else (e.g. 2606 = 2026-06 expiry) keeps its suffix.
    if expiry in ("", "0", "00", "000"):
        return f"kq_m_{canonical_exch}_{product.lower()}"
    return f"kq_m_{canonical_exch}_{product.lower()}{expiry}"


def _parse_qveris_time(ts: str) -> int:
    """Qveris ts is "YYYY-MM-DD HH:MM" or "YYYY-MM-DD HH:MM:SS" in CN local.
    Returns UTC epoch seconds."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            naive = datetime.strptime(ts, fmt)
            return int(naive.replace(tzinfo=CN_TZ).timestamp())
        except ValueError:
            continue
    raise ValueError(f"unrecognized qveris time format: {ts!r}")


def _qveris_call(thscode: str, starttime: str, endtime: str, interval: str) -> list[dict]:
    """Call qveris CLI, fetch full content if truncated. Returns raw bar dicts."""
    if not os.environ.get("QVERIS_API_KEY"):
        raise RuntimeError("QVERIS_API_KEY env var not set — run via scripts/_with_creds.sh qveris")
    params = json.dumps({
        "codes": thscode,
        "starttime": starttime,
        "endtime": endtime,
        "interval": interval,
    })
    # Pass --timeout to the qveris CLI itself so it doesn't abort the wide
    # backfill calls this fetcher is designed to support. The Python
    # subprocess timeout is set higher so it acts as a watchdog only
    # (codex 2026-05-26 review).
    proc = subprocess.run(
        ["qveris", "call", "ths_ifind.hf_basic_quotation.v1",
         "--json", "--params", params, "--timeout", "300"],
        capture_output=True, text=True, timeout=360,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"qveris CLI failed (exit {proc.returncode}): {proc.stderr[:500]}")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"qveris response not JSON: {e} — stdout head: {proc.stdout[:200]}")

    if not payload.get("success"):
        err = payload.get("error_message") or payload.get("result", {}).get("error_details", "")
        raise RuntimeError(f"qveris call failed: {err[:300]}")
    result = payload.get("result", {})
    full_url = result.get("full_content_file_url")
    if full_url:
        # CLI truncated; download full data from OSS
        with urllib.request.urlopen(full_url, timeout=120) as resp:
            data = json.loads(resp.read())
    else:
        data = result.get("data") or []
    if not isinstance(data, list):
        raise RuntimeError(f"qveris data not a list: type={type(data).__name__}")
    return data


def _to_canonical_bars(rows: list[dict]) -> list[dict]:
    """Map qveris ts/fields to canonical bar dicts.

    Skips rows missing any of OHLC — a 0-priced placeholder bar would
    cascade into MACD nans / wild divergence signals downstream (codex
    2026-05-26 review). Volume can legitimately be 0 (e.g. inter-session
    gap bar) so it gets defaulted, but prices must be real.
    """
    bars = []
    skipped = 0
    for r in rows:
        if r.get("time") is None:
            continue
        o_raw, h_raw, l_raw, c_raw = (
            r.get("开盘价"), r.get("最高价"), r.get("最低价"), r.get("收盘价"),
        )
        if any(v is None or v == "" for v in (o_raw, h_raw, l_raw, c_raw)):
            skipped += 1
            continue
        try:
            bars.append({
                "time": _parse_qveris_time(r["time"]),
                "open": float(o_raw),
                "high": float(h_raw),
                "low":  float(l_raw),
                "close": float(c_raw),
                "volume": int(r.get("成交量") or 0),
            })
        except (TypeError, ValueError) as e:
            skipped += 1
            print(f"WARN: skipping bad-typed row: {r} ({e})", file=sys.stderr)
    if skipped > 0:
        print(f"    skipped {skipped} rows with missing/invalid OHLC", file=sys.stderr)
    bars.sort(key=lambda b: b["time"])
    return bars


def _month_chunks(start: str, end: str) -> list[tuple[str, str]]:
    """Split [start, end] into calendar-month (startdate, enddate) pairs.

    Each chunk covers ≤ ~22 trading days so history_quotation.v1 returns
    data in-memory without triggering the OSS URL path (which returns 403).
    """
    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    chunks: list[tuple[str, str]] = []
    y, m = s.year, s.month
    while True:
        chunk_s = date(y, m, 1)
        if chunk_s > e:
            break
        last_day = monthrange(y, m)[1]
        chunk_e = date(y, m, last_day)
        chunks.append((max(chunk_s, s).isoformat(), min(chunk_e, e).isoformat()))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return chunks


def _qveris_history_call(thscode: str, startdate: str, enddate: str) -> list[dict]:
    """Call cn_financial_pro.history_quotation.v1 for one calendar-month chunk.

    Range must stay ≤ ~1 month. If the provider returns an OSS URL (triggered
    for larger ranges), this function raises because that OSS endpoint returns
    403 for history_quotation.v1.
    """
    if not os.environ.get("QVERIS_API_KEY"):
        raise RuntimeError("QVERIS_API_KEY env var not set — run via scripts/_with_creds.sh qveris")
    params = json.dumps({
        "codes": thscode,
        "startdate": startdate,
        "enddate": enddate,
        "interval": "D",
        "fill": "Blank",  # only real trading days; fill=Previous (default) fails for CN futures
    })
    proc = subprocess.run(
        ["qveris", "call", "cn_financial_pro.history_quotation.v1",
         "--json", "--params", params, "--timeout", "120"],
        capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"qveris CLI failed (exit {proc.returncode}): {proc.stderr[:500]}")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"qveris response not JSON: {exc}") from exc
    if not payload.get("success"):
        err = payload.get("error_message") or payload.get("result", {}).get("error_details", "")
        raise RuntimeError(f"qveris history call failed: {err[:300]}")
    result = payload.get("result", {})
    if "full_content_file_url" in result:
        raise RuntimeError(
            f"OSS URL triggered for {thscode} {startdate}→{enddate} — chunk is too large; "
            "cn_financial_pro.history_quotation.v1 OSS returns 403"
        )
    data = result.get("data") or [[]]
    if not isinstance(data, list) or not data:
        raise RuntimeError(f"unexpected data structure from history_quotation.v1")
    inner = data[0]
    return inner if isinstance(inner, list) else data


def _to_canonical_daily_bars(rows: list[dict]) -> list[dict]:
    """Map history_quotation.v1 daily rows to canonical bar dicts.

    Skips zero-price placeholder rows (open==0 and close==0) which the
    provider emits for non-trading days when fill=Previous is in effect.
    """
    bars = []
    skipped = 0
    for r in rows:
        t = r.get("time")
        if not t:
            continue
        o_raw, h_raw, l_raw, c_raw = r.get("open"), r.get("high"), r.get("low"), r.get("close")
        if any(v is None for v in (o_raw, h_raw, l_raw, c_raw)):
            skipped += 1
            continue
        try:
            o, h, l, c = float(o_raw), float(h_raw), float(l_raw), float(c_raw)
        except (TypeError, ValueError) as exc:
            skipped += 1
            print(f"WARN: skipping unparse-able daily row: {r} ({exc})", file=sys.stderr)
            continue
        if o == 0.0 and c == 0.0:
            skipped += 1
            continue
        try:
            naive = datetime.strptime(str(t), "%Y-%m-%d")
            # Stamp at 07:00 UTC = 15:00 CST (CN futures session close).
            # Midnight UTC (00:00 UTC = 08:00 CST) is before the day session
            # opens, so enrich_with_lower_tf(..., grace_minutes=30) would cut
            # off before any same-day 60min/15min bars are visible.  Session
            # close (07:00 UTC) ensures the full day session is included in
            # the [signal_t, signal_t+30m] slice window.
            ts = int(naive.replace(hour=7, tzinfo=timezone.utc).timestamp())
        except ValueError as exc:
            skipped += 1
            print(f"WARN: bad date {t!r} in daily row: {exc}", file=sys.stderr)
            continue
        bars.append({
            "time": ts,
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": int(r.get("volume") or 0),
        })
    if skipped:
        print(f"    skipped {skipped} zero-price/invalid daily rows", file=sys.stderr)
    bars.sort(key=lambda b: b["time"])
    return bars


def fetch_daily(thscode: str, start: str, end: str) -> Path:
    """Fetch daily bars from cn_financial_pro.history_quotation.v1 month by month.

    The endpoint's OSS URL returns 403, so we stay in-memory by chunking
    into calendar-month segments (≤ ~22 trading days each, well under the
    20 KB threshold that triggers OSS offloading).
    """
    chunks = _month_chunks(start[:10], end[:10])
    print(f"  fetching {thscode} daily {start} → {end} ({len(chunks)} monthly chunks) ...")
    all_rows: list[dict] = []
    for chunk_start, chunk_end in chunks:
        raw = _qveris_history_call(thscode, chunk_start, chunk_end)
        all_rows.extend(raw)
    bars = _to_canonical_daily_bars(all_rows)
    # Deduplicate by timestamp (month boundaries never overlap, but guard anyway)
    seen: set[int] = set()
    unique: list[dict] = []
    for b in bars:
        if b["time"] not in seen:
            seen.add(b["time"])
            unique.append(b)
    bars = unique
    print(f"    got {len(bars)} daily bars")
    if not bars:
        raise RuntimeError(f"empty daily bars for {thscode} — refusing to write snapshot")
    payload = {
        "symbol": _sanitize_thscode(thscode),
        "thscode": thscode,
        "resolution": "daily",
        "source": "qveris",
        "fetched_at_data_ts": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "bars": bars,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / f"{_sanitize_thscode(thscode)}_daily.json"
    out.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"    → {out}")
    return out


def fetch(thscode: str, tf: str, start: str, end: str) -> Path:
    """Fetch one symbol-tf-range, write snapshot, return path."""
    interval = TF_TO_QVERIS_INTERVAL[tf]
    # qveris wants HH:MM:SS, allow date-only inputs. Use 00:00:00 lower
    # bound so CN futures night-session bars (21:00 prev day → 02:30
    # next day on SHFE/DCE/INE) on the first calendar day are NOT
    # dropped (codex 2026-05-26 review).
    if "T" in start or " " in start:
        starttime = start.replace("T", " ")
    else:
        starttime = f"{start} 00:00:00"
    if "T" in end or " " in end:
        endtime = end.replace("T", " ")
    else:
        endtime = f"{end} 23:59:59"
    print(f"  fetching {thscode} {tf} {starttime} → {endtime} ...")
    raw_rows = _qveris_call(thscode, starttime, endtime, interval)
    bars = _to_canonical_bars(raw_rows)
    print(f"    got {len(bars)} bars")
    # Refuse to overwrite an existing valid snapshot with an empty one —
    # an empty response from a bad symbol / transient provider issue /
    # everything-skipped row would silently wipe historical data
    # (codex 2026-05-26 review).
    if not bars:
        raise RuntimeError(
            f"empty bars for {thscode} {tf} — refusing to write/overwrite snapshot"
        )
    payload = {
        "symbol": _sanitize_thscode(thscode),
        "thscode": thscode,
        "resolution": TF_TO_SUFFIX[tf],
        "source": "qveris",
        "fetched_at_data_ts": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "bars": bars,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / f"{_sanitize_thscode(thscode)}_{TF_TO_SUFFIX[tf]}.json"
    out.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"    → {out}")
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("thscodes", nargs="+",
                   help="THS codes, e.g. AU00.SHF M00.DCE IF00.CFE")
    _intraday_choices = sorted(TF_TO_QVERIS_INTERVAL.keys())
    p.add_argument("--tf", nargs="+", required=True,
                   choices=_intraday_choices + ["daily"],
                   help="timeframes: 1min/15min/60min (intraday) or 'daily'")
    p.add_argument("--start", required=True, help="YYYY-MM-DD (or with HH:MM:SS)")
    p.add_argument("--end", required=True, help="YYYY-MM-DD (or with HH:MM:SS)")
    args = p.parse_args()

    failures = 0
    for thscode in args.thscodes:
        for tf in args.tf:
            try:
                if tf == "daily":
                    fetch_daily(thscode, args.start, args.end)
                else:
                    fetch(thscode, tf, args.start, args.end)
            except Exception as e:
                failures += 1
                print(f"ERROR {thscode} {tf}: {type(e).__name__}: {e}", file=sys.stderr)
    if failures:
        print(f"\n{failures} fetch(es) failed — see errors above", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
