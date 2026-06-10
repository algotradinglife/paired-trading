"""Validated DD-line option exit simulator (take1/take2/stop), extracted from
sweep_ddline_options.py so the attribution harness and the sweep share one
implementation. Operates on an OPTION daily-OHLC frame."""
from __future__ import annotations

import pandas as pd


def simulate_entry(
    daily: pd.DataFrame,
    entry: dict,
    take1_mult: float,
    take2_mult: float,
    max_hold: int,
) -> dict:
    """Simulate one entry. Returns result dict with pnl metrics.

    entry = {entry_idx, entry_price, stop_price}. Banks take1 (0.5 size) at
    take1_mult, remainder at take2_mult; stop is a hard exit; otherwise marks
    the residual to close at the hold boundary (take1 partial already banked).
    """
    idx = entry["entry_idx"]
    ep = entry["entry_price"]
    sp = entry["stop_price"]
    t1 = ep * take1_mult
    t2 = ep * take2_mult

    risk = ep - sp
    if risk <= 0:
        return {**entry, "mult": 0.0, "r": 0.0, "exit_reason": "no_risk",
                "take1": False, "take2": False, "exit_day": 0}

    size = 1.0
    proceeds = 0.0
    take1_done = take2_done = False
    exit_day = max_hold
    exit_reason = "maxhold"

    for offset in range(1, max_hold + 1):
        j = idx + offset
        if j >= len(daily):
            exit_day = offset - 1
            exit_reason = "data_end"
            break

        lo = float(daily["low"].iloc[j])
        hi = float(daily["high"].iloc[j])
        cl = float(daily["close"].iloc[j])

        if lo <= sp and size > 0:
            proceeds += sp * size
            size = 0.0
            exit_day = offset
            exit_reason = "stop"
            break

        if not take1_done and hi >= t1 and size >= 0.5:
            proceeds += t1 * 0.5
            size -= 0.5
            take1_done = True

        if not take2_done and hi >= t2 and size > 0:
            proceeds += t2 * size
            size = 0.0
            take2_done = True
            exit_day = offset
            exit_reason = "take2"
            break

    if size > 0:
        final_idx = min(idx + exit_day, len(daily) - 1)
        proceeds += float(daily["close"].iloc[final_idx]) * size

    net = proceeds - ep
    mult = proceeds / ep if ep > 0 else 0.0
    r = net / risk

    return {
        **entry,
        "proceeds": round(proceeds, 1),
        "net": round(net, 1),
        "mult": round(mult, 3),
        "r": round(r, 2),
        "exit_reason": exit_reason,
        "take1": take1_done,
        "take2": take2_done,
        "exit_day": exit_day,
    }
