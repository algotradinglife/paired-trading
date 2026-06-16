"""IV-regime gate for the Feitian options chain — Rule 2 of card t_044a6019.

Buying naked OTM calls when signal-day implied vol sits in the upper tail of the
instrument's OWN prior signal-day IVs is systematically -EV: you pay rich convexity, and
high signal-day IV correlates with topping/stress regimes where breakouts fail more often.

The philosopher validated this in premium space on REAL option K-line (not Black-76, to
avoid the MODEL_DOMINATED trap), look-ahead-free via a causal expanding-window IV-rank
(`runs/_replica/feitian_h5_causal.py`, warmup=40):
  - au: keep rank<=0.66 → +1.47R (34% kept) vs all +0.77R; low-rank<0.33 → +1.57R
  - ag: keep rank<=0.66 → +0.25R (73% kept) vs all +0.04R — rescues ag from marginal
  monotone: lower signal-day IV-rank → higher premium-runner EV, both instruments.

This module is the PURE, deployable gate logic. Sourcing the signal-day IV (Black-76
back-out from the option close — see `engine/options/black76.py` / `cn_*_selector.estimate_iv`)
and the per-instrument prior-IV history is the caller's job; keeping the gate pure makes it
unit-testable without the option-data path and reusable across instruments.

Caveats (carry into any deployment): daily resolution, no bid/ask (premium leg OHLC only),
threshold 0.66 is the philosopher's split — re-confirm on more regimes; the tick-stop "命门"
(Rule §1) remains data-blocked and is NOT this gate.
"""
from __future__ import annotations

import math

DEFAULT_WARMUP = 40        # signals needed before a rank is meaningful (matches harness)
DEFAULT_MAX_RANK = 0.66    # drop signals whose signal-day IV-rank exceeds this (upper third)


def causal_iv_rank(
    current_iv: float | None,
    prior_ivs: list[float],
    warmup: int = DEFAULT_WARMUP,
) -> float | None:
    """Causal expanding-window IV-rank of `current_iv` among `prior_ivs` (this instrument's
    EARLIER signal-day IVs only — no look-ahead). Returns the fraction of prior IVs strictly
    below current, or None when there is too little history (< `warmup`) to rank against.

    Caller contract: pass ONLY IVs from signals strictly before this one, in any order; never
    include the current signal. Mirrors feitian_h5_causal.py exactly (strict `<`, denominator
    = all priors)."""
    # non-finite (None/NaN/inf) current IV is unrankable → None, so the gate skips it
    # conservatively rather than treating NaN as the cheapest possible regime (rank 0.0).
    if current_iv is None or not math.isfinite(current_iv):
        return None
    finite_priors = [x for x in prior_ivs if x is not None and math.isfinite(x)]
    n = len(finite_priors)
    if n < warmup:
        return None
    return sum(1 for x in finite_priors if x < current_iv) / n


def iv_regime_keep(
    rank: float | None,
    max_rank: float = DEFAULT_MAX_RANK,
    allow_during_warmup: bool = False,
) -> bool:
    """Gate decision: True = take the signal (IV cheap enough), False = drop.
    `rank` None means warmup (insufficient prior IV history) — controlled by
    `allow_during_warmup` (default False = conservatively skip until rankable, since the whole
    edge is conditioning on cheap IV and we can't assert that without history)."""
    if rank is None:
        return allow_during_warmup
    return rank <= max_rank


def iv_regime_decision(
    current_iv: float | None,
    prior_ivs: list[float],
    *,
    warmup: int = DEFAULT_WARMUP,
    max_rank: float = DEFAULT_MAX_RANK,
    allow_during_warmup: bool = False,
) -> dict:
    """Convenience wrapper: returns {iv_rank, keep, reason} for annotating a scored record.
    `reason` is None when kept, else a short drop reason for the advisory trail."""
    rank = causal_iv_rank(current_iv, prior_ivs, warmup=warmup)
    keep = iv_regime_keep(rank, max_rank=max_rank, allow_during_warmup=allow_during_warmup)
    if keep:
        reason = None
    elif rank is None:
        reason = f"iv_warmup(<{warmup} prior signals)"
    else:
        reason = f"iv_rank_rich({rank:.2f}>{max_rank})"
    return {"iv_rank": rank, "keep": keep, "reason": reason}
