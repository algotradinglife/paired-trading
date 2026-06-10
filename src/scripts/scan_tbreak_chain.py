"""Scan all pools for divergence-alert × trendline-break chain events.

Phase A deliverable: candidate-event lists (per pool, per symbol) for the
post-migration premium-space harness. NO EV claims here.

Usage:
    uv run python scripts/scan_tbreak_chain.py
    uv run python scripts/scan_tbreak_chain.py --pool CN_COMMODITY --since 2021-01-04
    uv run python scripts/scan_tbreak_chain.py -o ../data/review/tbreak_chain_events.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data import bar_loader
from engine.divergence.alert_chain import combine, divergence_alerts
from engine.divergence.tbreak_detector import TBreakDetector

DEFAULT_BARS_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "data" / "review" / "tbreak_chain_events.json"

# Mirrors score_today.py POOLS / POOL_INSTRUMENT_CLASS (2026-06-10).
POOLS: dict[str, list[str]] = {
    "US": ["SPY", "QQQ", "IWM", "DIA", "GLD", "GDX", "XLF", "XLK", "TLT",
           "NVDA", "XLB", "XLE", "XLRE", "XLU"],
    "CN_COMMODITY": [
        "kq_m_shfe_rb", "kq_m_shfe_cu", "kq_m_shfe_au", "kq_m_shfe_ag",
        "kq_m_dce_m", "kq_m_dce_i", "kq_m_dce_j", "kq_m_dce_jm",
        "kq_m_dce_p", "kq_m_dce_y",
        "kq_m_czce_ta", "kq_m_czce_ma", "kq_m_czce_cf", "kq_m_czce_sr",
        "kq_m_ine_sc",
    ],
    "CN_BOND": ["kq_m_cffex_tf", "kq_m_cffex_t", "kq_m_cffex_ts"],
}
POOL_INSTRUMENT_CLASS: dict[str, str] = {
    "US": "us_equity",
    "CN_COMMODITY": "cn_futures",
    "CN_BOND": "cn_bond",
}


def scan_symbol(sym: str, instrument_class: str, bars_dir: Path,
                since: str, lookback: int) -> list[dict] | None:
    bars = bar_loader.load_bars_quant_or_json(sym, "_daily", bars_dir)
    if bars is None or len(bars) < 80:
        return None
    alerts = divergence_alerts(bars, instrument_class=instrument_class)
    tbreaks = TBreakDetector().scan(bars)
    events = combine(alerts, tbreaks, lookback=lookback)
    out = []
    for ev in events:
        ts = ev.tbreak.timestamp
        if str(ts.date()) < since:
            continue
        out.append({
            "symbol": sym,
            "candidate": ev.candidate,
            "break_date": str(ts.date()),
            "break_close": ev.tbreak.features.get("close"),
            "alert_date": str(ev.alert.timestamp.date()),
            "alert_level": ev.alert.level,
            "alert_subtype": ev.alert.subtype,
            "alert_confidence": round(ev.alert.confidence, 3),
            "gap_bars": ev.gap_bars,
            "line": {k: ev.tbreak.features.get(k) for k in (
                "kind", "anchor_idx1", "anchor_price1", "anchor_idx2",
                "anchor_price2", "slope", "line_value", "touches")},
        })
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool", choices=sorted(POOLS), default=None,
                        help="single pool (default: all)")
    parser.add_argument("--since", default="2021-01-04")
    parser.add_argument("--lookback", type=int, default=20)
    parser.add_argument("--bars-dir", type=Path, default=DEFAULT_BARS_DIR)
    parser.add_argument("-o", "--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    pools = {args.pool: POOLS[args.pool]} if args.pool else POOLS
    result: dict[str, dict[str, list[dict]]] = {}
    for pool, symbols in pools.items():
        icls = POOL_INSTRUMENT_CLASS[pool]
        result[pool] = {}
        for sym in symbols:
            events = scan_symbol(sym, icls, args.bars_dir, args.since, args.lookback)
            if events is None:
                print(f"  [skip] {sym}: no/short bars", file=sys.stderr)
                continue
            result[pool][sym] = events

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1, ensure_ascii=False))
    print(f"wrote {args.out}")

    # Sanity summary: events/year per pool+candidate. Spec expectation:
    # single digits to a few tens per symbol-year; 0 everywhere or 100s
    # per symbol-year => parameter or bug suspicion.
    print(f"\n{'pool':14s} {'candidate':16s} {'year':6s} {'n':>4s}")
    for pool, by_sym in result.items():
        counter: Counter[tuple[str, str]] = Counter()
        n_syms = max(1, len(by_sym))
        for sym, events in by_sym.items():
            for ev in events:
                counter[(ev["candidate"], ev["break_date"][:4])] += 1
        for (cand, year), n in sorted(counter.items()):
            print(f"{pool:14s} {cand:16s} {year:6s} {n:4d}  "
                  f"(~{n / n_syms:.1f}/symbol)")


if __name__ == "__main__":
    main()
