"""Attribution backtest for score_today's ag/au options_calls emission.
Replays the live emission, prices each Rank-1 OTM call (real data + Black-76
fallback), simulates the validated DD-line exit, aggregates IS/OOS folds.

Spec: docs/superpowers/specs/2026-06-10-options-attribution-design.md

Fixes applied 2026-06-11 per review t_54083f1a:
  - AC-3: entry on next tradable bar close (not signal-day close); transaction
    costs (commission + slippage bps); gross and net metrics reported; verdict
    based on net metrics.
  - AC-4: verdict downgraded to REGIME_ONLY when modeled_fraction > 0.5;
    PROMOTE never emitted from model-dominated results."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
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

# AC-3: avoid signal-day close bias — enter on next tradable bar's close.
# 0 = signal-day close (old behaviour), 1 = next bar close (recommended).
ENTRY_OFFSET = 1

# AC-3: round-trip transaction costs (commission + slippage in basis points).
# Aggressive estimate: 10 bps commission + 10 bps slippage = 20 bps round-trip.
COMMISSION_BPS = 10
SLIPPAGE_BPS = 10
ROUND_TRIP_COST_BPS = COMMISSION_BPS + SLIPPAGE_BPS


def fold_of(year: int) -> str:
    return "is" if year <= IS_CUTOFF_YEAR else "oos"


def _entry_for_path(opt: "pd.DataFrame", *, tick: float, stop_ticks: int) -> dict | None:
    """Entry dict for simulate_entry, in GROSS price space.

    Returns None when the path has no bar at ENTRY_OFFSET (codex P2:
    falling back to row 0 would reintroduce the signal-day-close
    look-ahead the offset exists to avoid) or the offset close is
    non-positive.  Costs are NOT applied here — the simulation runs on
    gross prices and _net_mult applies the round trip once at the end
    (codex P2: a cost-adjusted entry fed into simulate_entry made
    _net_mult double-count the entry side and inflated stop/take
    thresholds).
    """
    if len(opt) <= ENTRY_OFFSET:
        return None
    entry_price = float(opt["close"].iloc[ENTRY_OFFSET])
    if entry_price <= 0:
        return None
    return {
        "entry_idx": ENTRY_OFFSET,
        "entry_price": entry_price,
        "stop_price": entry_price - stop_ticks * tick,
    }


def _net_mult(gross_mult: float) -> float:
    """Net premium multiple accounting for round-trip transaction costs.

    Half the round-trip cost is applied at entry (buying the option at
    a slightly worse price) and half at exit (selling at a slightly
    worse price).  For a 20 bps round trip:
      net_mult = gross_mult * (1 - 0.001) / (1 + 0.001)
               ≈ gross_mult * 0.998
    """
    half = ROUND_TRIP_COST_BPS / 20_000.0
    return round(gross_mult * (1.0 - half) / (1.0 + half), 4)


def verdict_for(is_ev: float, oos_ev: float, *, model_dominated: bool = False) -> str:
    """EV_mult > 1.0 = profit.

    When model_dominated is True (modeled_fraction > 0.5), PROMOTE is
    never returned — the verdict is capped at REGIME_ONLY (monitoring-grade)
    per AC-4.  Only market-backed results may reach PROMOTE."""
    if model_dominated:
        if oos_ev > 1.0:
            return "REGIME_ONLY"
        return "REJECT"
    # Market-backed (or fully market) verdicts
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


def _expiry_for_month(month_yymm: str, underlying: str):
    year, month = 2000 + int(month_yymm[:2]), int(month_yymm[2:])
    fn = _expiry_date_for_month if underlying == "ag" else _expiry_date_for_month_au
    return fn(year, month)


def _snap_to_listed(
    store, underlying: str, contract_sym: str, strike: float, spot: float,
    sig_date, *, dte_window: tuple[int, int] = (20, 75), min_cover: int = 5,
):
    """Snap a theoretical selector contract to a LISTED, DATA-COVERED one.

    The selectors pick expiry by DTE arithmetic and strikes by rounded
    %OTM — blind to SHFE listings (au options list only every other
    month; OPTIONS EXPIRE ~A MONTH EARLIER than their futures; strikes
    only as listed). Attribution must measure tradable contracts:
    prefer the nearest listed month inside the DTE window whose chain
    has >= min_cover bars from the signal date, then the nearest listed
    OTM strike. The month's OPTION expiry is proxied by its chain's
    LAST BAR DATE (the option's actual last trading day in data) —
    the futures-month expiry functions are ~a month late for options.

    Returns {contract_sym, strike, expiry_month, snapped} or None when
    nothing covered is in window — callers keep the theoretical
    contract then (pre-2024 history is absent from the store, which
    does not mean it was unlisted).
    """
    def covered(sym: str) -> bool:
        df = store.load_contract_daily(sym)
        return df is not None and len(df[df["date"] >= sig_date]) >= min_cover

    if covered(contract_sym):
        m = contract_sym.rstrip("0123456789")  # "ag2408c"
        return {"contract_sym": contract_sym, "strike": strike,
                "expiry_month": m[len(underlying):-1], "snapped": False}

    calls = [c for c in store.catalog(underlying) if c.opt_type == "C"]
    lo, hi = dte_window
    by_month: dict[str, list] = {}
    for c in calls:
        by_month.setdefault(c.underlying_month, []).append(c)

    def month_option_dte(cs: list) -> int | None:
        last = None
        for c in cs:
            df = store.load_contract_daily(c.contract_sym)
            if df is None or df.empty:
                continue
            d = df["date"].iloc[-1]
            if last is None or d > last:
                last = d
        return None if last is None else (last - sig_date).days

    in_window = sorted(
        (dte, month, cs)
        for month, cs in by_month.items()
        if (dte := month_option_dte(cs)) is not None and lo <= dte <= hi
    )
    for _, month, cs in in_window:   # nearest covered option expiry wins
        otm = [c for c in cs if c.strike > spot and covered(c.contract_sym)]
        if otm:
            best = min(otm, key=lambda c: abs(c.strike - strike))
            return {"contract_sym": best.contract_sym, "strike": best.strike,
                    "expiry_month": month, "snapped": True}
    return None


def _cell(rows: list[dict], key: str = "mult") -> dict:
    """:param key: 'mult' for gross, 'net_mult' for net."""
    if not rows:
        return {"n": 0, "ev_mult": None, "win_pct": None}
    mults = [t[key] for t in rows]
    return {"n": len(rows),
            "ev_mult": round(sum(mults) / len(mults), 3),
            "win_pct": round(sum(1 for m in mults if m > 1.0) / len(mults) * 100, 1)}


def _aggregate(underlying: str, trades: list[dict],
               market_n: int, model_n: int,
               gross: bool = False) -> dict:
    """Aggregate trades into a structured report.

    When ``gross`` is True, builds the gross-metrics report (pre-cost).
    When False, builds the net-metrics report (post-cost) and bases the
    verdict on net metrics.
    """
    key = "mult" if gross else "net_mult"
    label = "gross" if gross else "net"

    is_rows = [t for t in trades if fold_of(t["year"]) == "is"]
    oos_rows = [t for t in trades if fold_of(t["year"]) == "oos"]
    is_c, oos_c = _cell(is_rows, key), _cell(oos_rows, key)

    by_year: dict[int, list] = {}
    by_emitter: dict[str, list] = {}
    for t in trades:
        by_year.setdefault(t["year"], []).append(t)
        by_emitter.setdefault(t["emitter"], []).append(t)

    total = market_n + model_n
    modeled_fraction = round(model_n / total, 3) if total else None
    model_dominated = (modeled_fraction or 0.0) > 0.5

    # A fold with no trades counts as non-profitable (ev 0.0) for the verdict.
    verdict = verdict_for(is_c["ev_mult"] or 0.0, oos_c["ev_mult"] or 0.0,
                          model_dominated=model_dominated)
    reliability = ("MODEL_DOMINATED" if model_dominated else "MARKET_BACKED")

    entry_desc = f"next-bar close (offset={ENTRY_OFFSET}), Rank-1 OTM call (directional bottom, score>=3)"
    costs_desc = f"commission={COMMISSION_BPS}bps + slippage={SLIPPAGE_BPS}bps = {ROUND_TRIP_COST_BPS}bps r/t"

    base = {
        "lane": f"options_{underlying}",
        "underlying": UL_SYMBOL[underlying],
        "emission_binding": f"score_today.py:940-1303; cn_{underlying}_selector.select_otm_calls",
        "entry": entry_desc,
        "cost_model": costs_desc,
        "entry_offset": ENTRY_OFFSET,
        "exit": {"take1": EXIT["take1_mult"], "take2": EXIT["take2_mult"],
                 "stop_ticks": STOP_TICKS, "tick": TICK[underlying],
                 "max_hold_days": EXIT["max_hold"]},
        "pricing": {"market_n": market_n, "model_n": model_n,
                    "modeled_fraction": modeled_fraction},
    }

    suffix = "_gross" if gross else ""
    return {
        **base,
        "samples": {
            f"is{suffix}": is_c,
            f"oos{suffix}": oos_c,
            f"by_year{suffix}": {str(y): _cell(r, key) for y, r in sorted(by_year.items())},
        },
        "cells": {
            f"rank1{suffix}": _cell(trades, key),
            f"by_emitter{suffix}": {em: _cell(r, key) for em, r in sorted(by_emitter.items())},
        },
        f"verdict{suffix}": verdict,
        "reliability": reliability,
        f"verdict_reason{suffix}": (
            f"IS {label}_ev_mult={is_c['ev_mult']} (n={is_c['n']}), "
            f"OOS {label}_ev_mult={oos_c['ev_mult']} (n={oos_c['n']}); "
            f"modeled_fraction={modeled_fraction} -> reliability={reliability}. "
            f"Costs: {costs_desc}. "
            f"Entry: signal-day close offset {ENTRY_OFFSET} bar(s). "
            f"Verdict on {label} metrics."
        ),
        "data_snapshot": "2026-06-10",
    }


def _filter_emissions(emitted: list, since) -> list:
    """Restrict emissions to the market-covered era (sig_date >= since).

    The option store's history starts 2024-07; a full-window run is
    structurally MODEL_DOMINATED because 2021-2023 trades can never
    resolve to market data."""
    if since is None:
        return emitted
    return [e for e in emitted if e.sig_date >= since]


def run(underlying: str, *, since=None) -> dict:
    ul_sym = UL_SYMBOL[underlying]
    bars = bar_loader.load_bars_quant_or_json(ul_sym, "_daily", BARS_DIR)
    h = bar_loader.load_bars_quant_or_json(ul_sym, "_60", BARS_DIR)
    tick, iv, odir = TICK[underlying], IV_ASSUMPTION[underlying], _opt_dir(underlying)

    emitted = (replay_bpull(bars, h, underlying, ul_sym)
               + replay_pa_h2(bars, h, underlying, ul_sym)
               + replay_context_a(bars, h, underlying, ul_sym)
               + replay_divergence(bars, h, underlying))
    emitted = _filter_emissions(emitted, since)

    from data.bar_loader import DEFAULT_QUANT_ROOT
    from data.option_store import get_store
    opt_store = get_store(DEFAULT_QUANT_ROOT)

    trades: list[dict] = []
    market_n = model_n = snapped_n = 0
    for e in emitted:
        if not e.calls:
            continue
        rank1 = sorted(e.calls, key=lambda x: x["otm_pct"])[0]
        # Snap the theoretical selector contract to a LISTED one so the
        # market path measures tradable contracts (None -> keep the
        # theoretical contract; model fallback prices it as before).
        spot = float(rank1["strike"]) / (1.0 + rank1["otm_pct"] / 100.0)
        snap = _snap_to_listed(
            opt_store, underlying, rank1["contract_sym"],
            float(rank1["strike"]), spot, e.sig_date,
        )
        if snap is not None:
            sym, strike = snap["contract_sym"], float(snap["strike"])
            expiry = _expiry_for_month(snap["expiry_month"], underlying)
            if snap["snapped"]:
                snapped_n += 1
        else:
            sym, strike = rank1["contract_sym"], float(rank1["strike"])
            expiry = _expiry_from_calls(rank1, underlying)
        opt, src = premium_path(sym, strike=strike,
                                expiry=expiry, entry_date=e.sig_date, data_dir=odir,
                                underlying=bars, iv=iv, max_hold=EXIT["max_hold"])
        if opt is None or opt.empty:
            continue

        # AC-3: use next tradable bar close (offset ENTRY_OFFSET) as entry
        # to avoid signal-day close look-ahead bias.  Paths without a bar
        # at the offset are SKIPPED (no row-0 fallback); the simulation
        # runs on gross prices — costs are applied once in _net_mult.
        entry = _entry_for_path(opt, tick=tick, stop_ticks=STOP_TICKS)
        if entry is None:
            continue

        if src == "market":
            market_n += 1
        else:
            model_n += 1

        res = simulate_entry(opt, entry, **EXIT)

        # Gross multiple = what simulate_entry returns (pre-cost exit)
        gross_mult = res["mult"]
        # Net multiple: half the round-trip cost at entry and half at exit
        net_mult = _net_mult(gross_mult)

        trades.append({
            "year": e.sig_date.year,
            "emitter": e.emitter,
            "mult": round(gross_mult, 4),
            "net_mult": round(net_mult, 4),
            "source": src,
        })

    out = {
        "gross": _aggregate(underlying, trades, market_n, model_n, gross=True),
        "net": _aggregate(underlying, trades, market_n, model_n, gross=False),
    }
    for v in out.values():
        v["pricing"]["snapped_n"] = snapped_n
    return out


def main() -> None:
    global ENTRY_OFFSET, ROUND_TRIP_COST_BPS, IS_CUTOFF_YEAR
    ap = argparse.ArgumentParser()
    ap.add_argument("--underlying", choices=["ag", "au"], required=True)
    ap.add_argument("--out-json", type=Path, default=None)
    ap.add_argument("--entry-offset", type=int, default=ENTRY_OFFSET,
                    help="Bars to skip after signal date for entry (0=signal close, 1=next close)")
    ap.add_argument("--cost-bps", type=int, default=ROUND_TRIP_COST_BPS,
                    help="Round-trip cost in bps (default 20 = 10 commission + 10 slippage)")
    ap.add_argument("--since", type=date.fromisoformat, default=None,
                    help="Only signals on/after this date (market-era sub-window, "
                         "e.g. 2024-07-01 = start of option-store history)")
    ap.add_argument("--is-cutoff-year", type=int, default=IS_CUTOFF_YEAR,
                    help="IS <= this year, OOS after (re-split folds inside --since windows)")
    args = ap.parse_args()

    # Override globals from CLI args
    ENTRY_OFFSET = args.entry_offset
    ROUND_TRIP_COST_BPS = args.cost_bps
    IS_CUTOFF_YEAR = args.is_cutoff_year

    baseline = run(args.underlying, since=args.since)
    print(json.dumps(baseline, indent=2, default=str))
    if args.out_json:
        args.out_json.write_text(json.dumps(baseline, indent=2, default=str))


if __name__ == "__main__":
    main()
