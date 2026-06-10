"""Attribution backtest for score_today's ag/au options_calls emission.
Replays the live emission, prices each Rank-1 OTM call (real data + Black-76
fallback), simulates the validated DD-line exit, aggregates IS/OOS folds.
Spec: docs/superpowers/specs/2026-06-10-options-attribution-design.md"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data import bar_loader
from engine.options.cn_ag_selector import _expiry_date_for_month
from engine.options.cn_au_selector import _expiry_date_for_month_au
from engine.options.option_exit import simulate_entry
from engine.options.option_price_loader import IV_ASSUMPTION, premium_path
from engine.options.options_emission_replay import (
    replay_bpull, replay_context_a, replay_divergence, replay_pa_h2,
)

IS_CUTOFF_YEAR = 2023  # IS <= 2023, OOS >= 2024

BARS_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
TICK = {"ag": 1.0, "au": 2.0}
UL_SYMBOL = {"ag": "kq_m_shfe_ag", "au": "kq_m_shfe_au"}
EXIT = dict(take1_mult=2.0, take2_mult=4.0, max_hold=30)
STOP_TICKS = 5


def fold_of(year: int) -> str:
    return "is" if year <= IS_CUTOFF_YEAR else "oos"


def verdict_for(is_ev: float, oos_ev: float) -> str:
    """EV_mult > 1.0 = profit. PROMOTE iff both folds profitable; REGIME_ONLY
    iff only OOS; REJECT iff neither."""
    if is_ev > 1.0 and oos_ev > 1.0:
        return "PROMOTE"
    if oos_ev > 1.0:
        return "REGIME_ONLY"
    return "REJECT"


def _opt_dir(underlying: str) -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "options" / "cn" / underlying


def _expiry_from_calls(call: dict, underlying: str):
    """Derive the contract expiry date from the call's 'YYMM' expiry_month."""
    ym = str(call["expiry_month"])
    year, month = 2000 + int(ym[:2]), int(ym[2:])
    fn = _expiry_date_for_month if underlying == "ag" else _expiry_date_for_month_au
    return fn(year, month)


def _cell(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0, "ev_mult": None, "win_pct": None}
    mults = [t["mult"] for t in rows]
    return {"n": len(rows),
            "ev_mult": round(sum(mults) / len(mults), 3),
            "win_pct": round(sum(1 for m in mults if m > 1.0) / len(mults) * 100, 1)}


def _aggregate(underlying: str, trades: list[dict], market_n: int, model_n: int) -> dict:
    is_rows = [t for t in trades if fold_of(t["year"]) == "is"]
    oos_rows = [t for t in trades if fold_of(t["year"]) == "oos"]
    is_c, oos_c = _cell(is_rows), _cell(oos_rows)

    by_year: dict[int, list] = {}
    by_emitter: dict[str, list] = {}
    for t in trades:
        by_year.setdefault(t["year"], []).append(t)
        by_emitter.setdefault(t["emitter"], []).append(t)

    total = market_n + model_n
    modeled_fraction = round(model_n / total, 3) if total else None
    # A fold with no trades counts as non-profitable (ev 0.0) for the verdict.
    verdict = verdict_for(is_c["ev_mult"] or 0.0, oos_c["ev_mult"] or 0.0)
    return {
        "lane": f"options_{underlying}",
        "underlying": UL_SYMBOL[underlying],
        "emission_binding": f"score_today.py:940-1303; cn_{underlying}_selector.select_otm_calls",
        "entry": "signal-day close, Rank-1 OTM call (cn_metal bottom, score>=3)",
        "exit": {"take1": EXIT["take1_mult"], "take2": EXIT["take2_mult"],
                 "stop_ticks": STOP_TICKS, "tick": TICK[underlying],
                 "max_hold_days": EXIT["max_hold"]},
        "pricing": {"market_n": market_n, "model_n": model_n,
                    "modeled_fraction": modeled_fraction},
        "samples": {"is": is_c, "oos": oos_c,
                    "by_year": {str(y): _cell(r) for y, r in sorted(by_year.items())}},
        "cells": {"rank1": _cell(trades),
                  "by_emitter": {em: _cell(r) for em, r in sorted(by_emitter.items())}},
        "verdict": verdict,
        "verdict_reason": (f"IS ev_mult={is_c['ev_mult']} (n={is_c['n']}), "
                           f"OOS ev_mult={oos_c['ev_mult']} (n={oos_c['n']}); "
                           f"modeled_fraction={modeled_fraction}."),
        "data_snapshot": "2026-06-10",
    }


def run(underlying: str) -> dict:
    ul_sym = UL_SYMBOL[underlying]
    bars = bar_loader.load_bars_quant_or_json(ul_sym, "_daily", BARS_DIR)
    h = bar_loader.load_bars_quant_or_json(ul_sym, "_60", BARS_DIR)
    tick, iv, odir = TICK[underlying], IV_ASSUMPTION[underlying], _opt_dir(underlying)

    emitted = (replay_bpull(bars, h, underlying, ul_sym)
               + replay_pa_h2(bars, h, underlying, ul_sym)
               + replay_context_a(bars, h, underlying, ul_sym)
               + replay_divergence(bars, h, underlying))

    trades: list[dict] = []
    market_n = model_n = 0
    for e in emitted:
        if not e.calls:
            continue
        rank1 = sorted(e.calls, key=lambda x: x["otm_pct"])[0]
        expiry = _expiry_from_calls(rank1, underlying)
        opt, src = premium_path(rank1["contract_sym"], strike=float(rank1["strike"]),
                                expiry=expiry, entry_date=e.sig_date, data_dir=odir,
                                underlying=bars, iv=iv, max_hold=EXIT["max_hold"])
        if opt is None or opt.empty:
            continue
        entry_price = float(opt["close"].iloc[0])
        if entry_price <= 0:
            continue
        if src == "market":
            market_n += 1
        else:
            model_n += 1
        entry = {"entry_idx": 0, "entry_price": entry_price,
                 "stop_price": entry_price - STOP_TICKS * tick}
        res = simulate_entry(opt, entry, **EXIT)
        trades.append({"year": e.sig_date.year, "emitter": e.emitter,
                       "mult": res["mult"], "source": src})
    return _aggregate(underlying, trades, market_n, model_n)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--underlying", choices=["ag", "au"], required=True)
    ap.add_argument("--out-json", type=Path, default=None)
    args = ap.parse_args()
    baseline = run(args.underlying)
    print(json.dumps(baseline, indent=2, default=str))
    if args.out_json:
        args.out_json.write_text(json.dumps(baseline, indent=2, default=str))


if __name__ == "__main__":
    main()
