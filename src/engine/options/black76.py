"""Black-76 pricing + implied-vol inversion for options on futures.

SHFE/DCE/CZCE commodity options are European options on futures —
Black-76 is the correct model (the in-repo BS helpers price on spot;
see doc/design/paired_options_direction_2026-06-10.md §1.3 P3).
"""

from __future__ import annotations

import math


def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def black76_price(
    F: float, K: float, T: float, r: float, sigma: float, opt_type: str = "C"
) -> float:
    """Black-76 European option price on a futures contract.

    Args:
        F: futures price.
        K: strike.
        T: time to expiry in years.
        r: risk-free rate (continuous compounding) used for discounting.
        sigma: annualized volatility.
        opt_type: "C" or "P".

    Returns intrinsic (discounted) value when T<=0 or sigma<=0.
    """
    is_call = opt_type.upper() == "C"
    disc = math.exp(-r * max(T, 0.0))
    if T <= 0 or sigma <= 0:
        intrinsic = max(F - K, 0.0) if is_call else max(K - F, 0.0)
        return disc * intrinsic
    sqrt_T = math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * sigma * sigma * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    if is_call:
        return disc * (F * _ncdf(d1) - K * _ncdf(d2))
    return disc * (K * _ncdf(-d2) - F * _ncdf(-d1))


def implied_vol(
    option_price: float,
    F: float,
    K: float,
    T: float,
    r: float = 0.02,
    opt_type: str = "C",
) -> float | None:
    """Invert Black-76 for sigma via bisection.

    Returns None when the price is below discounted intrinsic, above the
    sigma=20.0 bound, or T<=0.
    """
    if T <= 0 or option_price <= 0:
        return None
    lo, hi = 1e-4, 20.0
    lo_px = black76_price(F, K, T, r, lo, opt_type)
    hi_px = black76_price(F, K, T, r, hi, opt_type)
    if option_price < lo_px - 1e-9 or option_price > hi_px + 1e-9:
        return None
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        px = black76_price(F, K, T, r, mid, opt_type)
        if abs(px - option_price) < 1e-9:
            return mid
        if px < option_price:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-10:
            break
    return 0.5 * (lo + hi)
