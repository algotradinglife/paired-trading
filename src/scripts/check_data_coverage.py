"""Read-only data-coverage check vs doc/data_gaps_for_pipeline_2026-06-11.md.

Run after a pipeline backfill completes to see what is satisfied:

    uv run python scripts/check_data_coverage.py [--root data/quant]

Prints one [ OK ]/[WARN]/[MISS] row per checklist item and exits 1 when
any REQUIRED item is MISS (WARNs never fail the run). Strictly read-only
— never writes to the store.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

# scripts/ is run as a file — make src importable
_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pandas as pd  # noqa: E402

from data import continuous  # noqa: E402
from data.option_store import OptionStore  # noqa: E402


@dataclass
class CheckResult:
    status: str          # "OK" | "WARN" | "MISS"
    detail: str
    start: date | None = None


# ---------------------------------------------------------------------------
# Probes
# ---------------------------------------------------------------------------

def check_continuous_coverage(
    root: Path, exchange: str, product: str, *,
    target_start: date, as_of: date,
) -> CheckResult:
    """Synthesized continuous daily series must span target_start → ~as_of."""
    try:
        df = continuous.synthesize_continuous(root, exchange, product, "D")
    except ValueError:
        return CheckResult("MISS", "no contract files", start=None)
    if df.empty:
        return CheckResult("MISS", "synthesis empty", start=None)
    start = df["datetime"].iloc[0].date()
    end = df["datetime"].iloc[-1].date()
    n = len(df)
    detail = f"{start} -> {end} ({n} bars)"
    if start > target_start:
        return CheckResult("MISS", f"{detail}; starts after {target_start}", start=start)
    if end < as_of - timedelta(days=7):
        return CheckResult("WARN", f"{detail}; stale end", start=start)
    return CheckResult("OK", detail, start=start)


def check_us_hourly_years(
    root: Path, ticker: str, *, years: tuple[int, ...],
    min_bars: dict | int = 3500,
) -> CheckResult:
    """Each year must have >= its min_bars hourly rows (hole detection).

    ``min_bars`` may be a dict keyed by year with a "default" entry —
    2021 nominal coverage starts mid-year and needs a lower floor.
    """
    path = Path(root) / "hour" / f"{ticker}.AMEX.parquet"
    if not path.exists():
        return CheckResult("MISS", "no hourly file")
    counts = (
        pd.read_parquet(path, columns=["datetime"])["datetime"]
        .dt.year.value_counts()
    )

    def floor(y: int) -> int:
        if isinstance(min_bars, dict):
            return min_bars.get(y, min_bars["default"])
        return min_bars

    holes = [y for y in years if int(counts.get(y, 0)) < floor(y)]
    if holes:
        return CheckResult(
            "MISS",
            "hole years: " + ", ".join(f"{y}={int(counts.get(y, 0))}" for y in holes),
        )
    return CheckResult("OK", f"{int(counts.sum())} bars, no holes")


def check_options_depth(
    root: Path, product: str, *, target_earliest: date,
) -> CheckResult:
    """Option chain must have puts AND history back to target_earliest."""
    store = OptionStore(root)
    cat = store.catalog(product)
    if not cat:
        return CheckResult("MISS", "no option contracts")
    problems = []
    types = {c.opt_type for c in cat}
    if "P" not in types:
        problems.append("no puts")
    if "C" not in types:
        problems.append("no calls")
    earliest: date | None = None
    for c in cat:
        df = store.load_contract_daily(c.contract_sym)
        if df is None or df.empty:
            continue
        d0 = df["date"].iloc[0]
        if earliest is None or d0 < earliest:
            earliest = d0
    if earliest is None:
        problems.append("all files empty")
    elif earliest > target_earliest:
        problems.append(f"history starts {earliest} (> {target_earliest})")
    if problems:
        return CheckResult("MISS", f"{len(cat)} contracts; " + "; ".join(problems))
    return CheckResult("OK", f"{len(cat)} contracts, history from {earliest}")


def check_oi_fraction(root: Path, exchange: str, product: str) -> CheckResult:
    """Fraction of futures contract files with any OI>0 (informational)."""
    contracts = continuous.discover_contracts(root, "daily", exchange, product)
    if not contracts:
        return CheckResult("MISS", "no contract files")
    nz = 0
    for p in contracts.values():
        oi = pd.read_parquet(p, columns=["open_interest"])["open_interest"]
        if (oi > 0).any():
            nz += 1
    frac = nz / len(contracts)
    detail = f"{nz}/{len(contracts)} files with OI"
    return CheckResult("OK" if frac >= 0.9 else "WARN", detail)


def _file_exists(root: Path, folder: str, name: str) -> CheckResult:
    ok = (Path(root) / folder / f"{name}.parquet").exists()
    return CheckResult("OK" if ok else "WARN", "present" if ok else "missing")


# ---------------------------------------------------------------------------
# Checklist (mirrors doc/data_gaps_for_pipeline_2026-06-11.md)
# ---------------------------------------------------------------------------

# (exchange, product, target_start, required)
_CN_CONTINUOUS = [
    # production pools — REQUIRED
    ("SHFE", "cu", date(2021, 9, 1), True),
    ("SHFE", "au", date(2021, 9, 1), True),
    ("SHFE", "ag", date(2021, 9, 1), True),
    ("INE",  "sc", date(2021, 9, 1), True),
    ("CFFEX", "TF", date(2021, 9, 1), True),
    ("CFFEX", "T",  date(2021, 9, 1), True),
    ("CFFEX", "TS", date(2021, 9, 1), True),
    # monitoring / climax pools — informational
    ("SHFE", "rb", date(2021, 9, 1), False),
    ("SHFE", "al", date(2021, 9, 1), False),
    ("SHFE", "ni", date(2021, 9, 1), False),
    ("DCE",  "m",  date(2021, 9, 1), False),
    ("DCE",  "i",  date(2021, 9, 1), False),
    ("DCE",  "j",  date(2021, 9, 1), False),
    ("DCE",  "jm", date(2021, 9, 1), False),
    ("DCE",  "p",  date(2021, 9, 1), False),
    ("DCE",  "y",  date(2021, 9, 1), False),
    ("CZCE", "CF", date(2021, 9, 1), False),
    ("CZCE", "RM", date(2021, 9, 1), False),
    ("CZCE", "SR", date(2021, 9, 1), False),
    ("CZCE", "TA", date(2021, 9, 1), False),
    ("CZCE", "MA", date(2021, 9, 1), False),
    ("CFFEX", "IF", date(2021, 9, 1), False),
    ("CFFEX", "IH", date(2021, 9, 1), False),
    ("CFFEX", "IC", date(2021, 9, 1), False),
    ("CFFEX", "IM", date(2022, 9, 1), False),  # listed 2022-07
]

_US_TICKERS = [
    "SPY", "QQQ", "IWM", "DIA", "GLD", "GDX", "XLF", "XLK",
    "NVDA", "XLB", "XLE", "XLRE", "XLU", "TLT",
]
_US_CORE = {"SPY", "QQQ", "IWM"}      # REQUIRED hourly integrity
_US_HOUR_YEARS = (2021, 2022, 2023, 2024, 2025)
# 2021 nominal coverage starts 2021-06 (half year)
_US_HOUR_MIN = {2021: 1800, "default": 3500}

# CN options: (product, target_earliest, required) — ag/au depth is the
# P0 attribution prerequisite; industrials are the put-research pool.
_CN_OPTIONS = [
    ("ag", date(2024, 7, 1), True),
    ("au", date(2024, 7, 1), True),
    ("cu", date(2024, 7, 1), False),
    ("rb", date(2024, 7, 1), False),
    ("i",  date(2024, 7, 1), False),
    ("m",  date(2024, 7, 1), False),
    ("al", date(2024, 7, 1), False),
    ("ni", date(2024, 7, 1), False),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path,
                    default=_SRC / "data" / "quant",
                    help="quant store root (default: data/quant symlink)")
    args = ap.parse_args()
    root = args.root
    as_of = date.today()
    failures = 0

    def emit(section: str, name: str, res: CheckResult, required: bool) -> None:
        nonlocal failures
        icon = {"OK": "[ OK ]", "WARN": "[WARN]", "MISS": "[MISS]"}[res.status]
        req = "*" if required else " "
        print(f"{icon}{req} {section:12s} {name:14s} {res.detail}")
        if required and res.status == "MISS":
            failures += 1

    print(f"# data coverage check — root={root}  as_of={as_of}")
    print("# '*' = required; exit 1 when any required item is MISS\n")

    for exch, prod, target, required in _CN_CONTINUOUS:
        res = check_continuous_coverage(
            root, exch, prod, target_start=target, as_of=as_of)
        emit("cn-cont", f"{exch}.{prod}", res, required)

    print()
    for t in _US_TICKERS:
        d = Path(root) / "daily" / f"{t}.AMEX.parquet"
        if not d.exists():
            emit("us-daily", t, CheckResult("MISS", "no daily file"), t in _US_CORE)
            continue
        res = check_us_hourly_years(
            root, t, years=_US_HOUR_YEARS, min_bars=_US_HOUR_MIN)
        emit("us-hourly", t, res, t in _US_CORE)
    print()
    for t in ("SPY", "QQQ", "IWM"):
        emit("us-15min", t, _file_exists(root, "min15", f"{t}.AMEX"), False)
        emit("us-weekly", t, _file_exists(root, "weekly", f"{t}.AMEX"), False)

    print()
    for prod, target, required in _CN_OPTIONS:
        res = check_options_depth(root, prod, target_earliest=target)
        emit("cn-options", prod, res, required)

    print()
    for exch, prod in (("SHFE", "cu"), ("SHFE", "ag"), ("CFFEX", "T")):
        emit("oi-resync", f"{exch}.{prod}", check_oi_fraction(root, exch, prod), False)

    print(f"\n{'FAIL' if failures else 'PASS'}: {failures} required item(s) missing")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
