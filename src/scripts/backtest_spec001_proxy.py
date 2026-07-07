"""backtest_spec001_proxy.py — DETERMINISTIC proxy backtest of SPEC-001 at scale (t_0da3b750, option A).

⚠️ This is NOT the philosopher LLM replica. It is a researcher-built **deterministic
approximation** of SPEC-001's codifiable rules (wedge/lower-boundary pullback + strong
bull signal bar + ≥2:1 structural target), run across the CN futures universe to give a
first-order, scale EV read while the faithful replica corpus (t_3d25c2f5) is pending.
Differences from the replica MUST be kept in mind: the fuzzy `win_rate_est ≥ 0.5` gate is
OMITTED (no LLM judgment), the three-push wedge is approximated by a lower-boundary + prior
swing-low (second-test) proxy, and PA context nuance is reduced to mechanical thresholds.
Treat the EV here as an independent sanity estimate, not the spec's verdict.

Deterministic rules (no-lookahead; all thresholds ATR-relative):
  Signal bar i (closed): body/range ≥ BODY_FRAC and close in upper 1/3 (close_pos ≥ CLOSE_POS).
  Context: over the prior LOOKBACK bars — (a) signal bar low within NEAR_LOW_ATR×ATR of the
    window low (at the lower boundary), (b) a prior swing high ≥ MIN_RANGE_ATR×ATR above that
    low occurring BEFORE the low (a real down-leg to fade), (c) [second-entry proxy] a prior
    swing low within NEAR_LOW_ATR×ATR of the window low (not the first probe).
  Order: entry = signal bar high; stop = signal bar low; target = prior swing high.
    Gate: fire only if payoff = (target-entry)/(entry-stop) ≥ PAYOFF_MIN (2.0). MIN_GAP between fires.
  Exit: reuse eval_spec001_ev.simulate_order (buy-stop entry, intrabar stop-first, timeout,
    data-exhausted → unresolved/excluded). Net R subtracts --cost-r.

Usage:
  cd src && python3 scripts/backtest_spec001_proxy.py --products ag au cu al rb i sc \
      --out data/review/spec001_proxy_ev.json   # quant store via philosopher tp.pa.cn_data
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from scripts.eval_spec001_ev import _DEFAULT_TP_SRC, _load_cn_window, _utc, simulate_order

# --- deterministic detector params (documented; ATR-relative) ---
ATR_PERIOD = 14
LOOKBACK = 40          # bars defining the recent down-leg / lower boundary
SWING_N = 3            # swing confirmation bars per side
NEAR_LOW_ATR = 1.0     # signal bar low within this×ATR of the window low
MIN_RANGE_ATR = 2.0    # prior swing high must be ≥ this×ATR above the window low
BODY_FRAC = 0.5        # strong bar: body/range
CLOSE_POS = 2.0 / 3.0  # close in upper 1/3 of range
PAYOFF_MIN = 2.0       # trader's-equation payoff gate (win_rate_est term omitted)
MIN_GAP = 10           # bars between fires (mirror replica selectivity)
DEFAULT_PRODUCTS = ("ag", "au", "cu", "al", "rb", "i", "sc")


def _atr(bars: list[dict], period: int = ATR_PERIOD) -> np.ndarray:
    h = np.array([b["high"] for b in bars], float)
    lo = np.array([b["low"] for b in bars], float)
    c = np.array([b["close"] for b in bars], float)
    prev_c = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum.reduce([h - lo, np.abs(h - prev_c), np.abs(lo - prev_c)])
    # span-EWM ATR (matches backtest_rr_pool.compute_atr convention)
    alpha = 2.0 / (period + 1)
    atr = np.empty_like(tr)
    atr[0] = tr[0]
    for i in range(1, len(tr)):
        atr[i] = alpha * tr[i] + (1 - alpha) * atr[i - 1]
    return atr


def _swing_lows(bars: list[dict], n: int = SWING_N) -> np.ndarray:
    lows = np.array([b["low"] for b in bars], float)
    idx = []
    for i in range(n, len(lows) - n):
        if lows[i] == lows[i - n:i + n + 1].min() and lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
            idx.append(i)
    return np.array(idx, dtype=int)


def detect_signals(bars: list[dict]) -> list[dict]:
    """Deterministic SPEC-001 proxy signals on one contract series (no-lookahead)."""
    n = len(bars)
    if n < LOOKBACK + ATR_PERIOD + 2:
        return []
    atr = _atr(bars)
    sl_idx = _swing_lows(bars)            # confirmed swing lows (offline; used only for i' < i)
    highs = np.array([b["high"] for b in bars], float)
    lows = np.array([b["low"] for b in bars], float)
    out = []
    last_fire = -10 ** 9
    for i in range(LOOKBACK, n - 1):
        if i - last_fire < MIN_GAP:
            continue
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        o, h, lo, c = bars[i]["open"], bars[i]["high"], bars[i]["low"], bars[i]["close"]
        rng = h - lo
        if rng <= 0:
            continue
        if abs(c - o) / rng < BODY_FRAC:           # strong body
            continue
        if (c - lo) / rng < CLOSE_POS:             # close upper 1/3
            continue
        w0 = i - LOOKBACK + 1
        win_low = lows[w0:i + 1].min()
        win_low_idx = w0 + int(np.argmin(lows[w0:i + 1]))
        if (lo - win_low) > NEAR_LOW_ATR * a:      # at the lower boundary
            continue
        if win_low_idx <= w0:                      # low at window start → no preceding down-leg
            continue
        # prior swing high = down-leg origin, must PRECEDE the low (highs STRICTLY before the
        # low bar; neither a post-low bounce nor the low bar's own high may validate the leg
        # or become the target — codex P2 x2). win_low_idx > w0 guaranteed above → non-empty.
        prior_high = highs[w0:win_low_idx].max()
        if (prior_high - win_low) < MIN_RANGE_ATR * a:
            continue
        # second-entry proxy: a prior confirmed swing low near the window low (not first probe)
        prior_sl = [j for j in sl_idx if w0 <= j < i and j + SWING_N <= i
                    and abs(lows[j] - win_low) <= NEAR_LOW_ATR * a]
        if not prior_sl:
            continue
        entry = float(h)
        stop = float(lo)
        target = float(prior_high)                 # structural target = pre-low swing high
        risk = entry - stop
        if risk <= 0:
            continue
        payoff = (target - entry) / risk
        if payoff < PAYOFF_MIN:                    # trader's-equation gate
            continue
        out.append({"i": i, "order_direction": "做多", "entry": entry,
                    "stop": stop, "target": target, "payoff": round(payoff, 3),
                    "ts": _utc(bars[i]["ts_open"])})
        last_fire = i
    return out


def _product(contract: str) -> str:
    return "".join(ch for ch in contract if not ch.isdigit())


def run(products: list[str], tp_src: Path, cost_r: float,
        max_wait_bars: int, max_hold_bars: int, dedup: bool) -> dict:
    load_cn_window = _load_cn_window(tp_src)
    sys.path.insert(0, str(tp_src))
    from tp.pa.cn_data import list_contracts          # noqa: E402
    contracts = [c for c in list_contracts("5min") if _product(c) in set(products)]
    rows = []
    seen = set()
    horizon = max_wait_bars + max_hold_bars
    for ci, contract in enumerate(contracts):
        bars = load_cn_window(contract, "5min", 200000)
        if not bars or len(bars) < LOOKBACK + ATR_PERIOD + 2:
            continue
        sigs = detect_signals(bars)
        for s in sigs:
            i = s["i"]
            key = (_product(contract), s["ts"].date())   # cross-expiry dedup by product+day
            if dedup and key in seen:
                continue
            fwd = bars[i: i + horizon + 5]
            sim = simulate_order(s, fwd, node_end=s["ts"], cost_r=cost_r,
                                 max_wait_bars=max_wait_bars, max_hold_bars=max_hold_bars)
            if sim is None:
                continue
            if dedup:
                seen.add(key)
            rows.append({"contract": contract, "product": _product(contract),
                         "ts": s["ts"].isoformat(), "payoff": s["payoff"], **sim})
        print(f"  [{ci+1}/{len(contracts)}] {contract}: {len(sigs)} sigs "
              f"(cum rows {len(rows)})", file=sys.stderr)
    return _summary(rows, products, cost_r)


def _stats(rs: list[dict]) -> dict:
    res = [r for r in rs if r.get("triggered") and r.get("resolved")]
    g = [r["gross_r"] for r in res]
    nr = [r["net_r"] for r in res]
    return {
        "n_signals": len(rs),
        "n_resolved": len(res),
        "n_unresolved": sum(1 for r in rs if not r.get("resolved")),
        "n_no_trigger": sum(1 for r in rs if r.get("exit_kind") == "no_trigger"),
        "win_rate": round(sum(1 for r in res if r["gross_r"] > 0) / len(res), 4) if res else None,
        "mean_gross_r": round(statistics.mean(g), 4) if g else None,
        "mean_net_r": round(statistics.mean(nr), 4) if nr else None,
        "median_gross_r": round(statistics.median(g), 4) if g else None,
        "exit_kinds": {k: sum(1 for r in res if r["exit_kind"] == k)
                       for k in ("target", "stop", "timeout")},
    }


def _summary(rows: list[dict], products: list[str], cost_r: float) -> dict:
    by_product = {}
    bp = defaultdict(list)
    for r in rows:
        bp[r["product"]].append(r)
    for p, rs in bp.items():
        by_product[p] = _stats(rs)
    return {
        "params": {
            "PROXY": "deterministic SPEC-001 approximation — NOT the philosopher replica; "
                     "win_rate_est gate omitted, wedge approximated",
            "products": products, "cost_r": cost_r,
            "detector": {"LOOKBACK": LOOKBACK, "NEAR_LOW_ATR": NEAR_LOW_ATR,
                         "MIN_RANGE_ATR": MIN_RANGE_ATR, "BODY_FRAC": BODY_FRAC,
                         "CLOSE_POS": round(CLOSE_POS, 3), "PAYOFF_MIN": PAYOFF_MIN,
                         "MIN_GAP": MIN_GAP},
        },
        "overall": _stats(rows),
        "by_product": by_product,
        "orders": rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--products", nargs="+", default=list(DEFAULT_PRODUCTS))
    ap.add_argument("--philosopher-src", type=Path, default=_DEFAULT_TP_SRC)
    ap.add_argument("--cost-r", type=float, default=0.0)
    ap.add_argument("--max-wait-bars", type=int, default=288)
    ap.add_argument("--max-hold-bars", type=int, default=288)
    ap.add_argument("--no-dedup", action="store_true", help="keep cross-expiry duplicate days")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    rep = run(args.products, args.philosopher_src, args.cost_r,
              args.max_wait_bars, args.max_hold_bars, dedup=not args.no_dedup)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rep, ensure_ascii=False, indent=2))
    o = rep["overall"]
    print(f"wrote {args.out}  (n_resolved={o['n_resolved']} win={o['win_rate']} "
          f"gross_ev={o['mean_gross_r']} net_ev={o['mean_net_r']} "
          f"exits={o['exit_kinds']})")


if __name__ == "__main__":
    main()
