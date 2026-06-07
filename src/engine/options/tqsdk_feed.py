"""TqSdk snapshot feed for CN option prices.

Fetches live (or most-recent) option bid/ask/last prices using TqSdk.
Falls back silently when TQ_USERNAME/TQ_PASSWORD are not set or TqSdk
raises an error (network down, market closed with stale quotes, etc.).
"""

from __future__ import annotations

import re


def _ag_to_tqsdk(contract_sym: str) -> str:
    """Convert internal ag option symbol to TqSdk format.

    Examples:
        ag2507c22700  → SHFE.ag2507C22700
        ag2510c10200  → SHFE.ag2510C10200
        ag2507p22700  → SHFE.ag2507P22700

    Rule: find the last 'c' or 'p' (case-insensitive) that separates the
    contract month from the strike, uppercase it, prefix with 'SHFE.'.
    """
    # Match: letters+digits (root+month), option type (c/p), strike digits
    m = re.match(r"^([a-zA-Z]+\d+)([cCpP])(\d+)$", contract_sym)
    if not m:
        raise ValueError(f"Cannot parse ag option symbol: {contract_sym!r}")
    root_month = m.group(1)       # e.g. "ag2507"
    opt_type = m.group(2).upper() # "C" or "P"
    strike = m.group(3)           # e.g. "22700"
    return f"SHFE.{root_month}{opt_type}{strike}"


def fetch_live_option_prices(
    contract_syms: list[str],
    timeout_sec: float = 15.0,
) -> dict[str, float | None]:
    """Fetch last/bid/ask price for each ag call contract via TqSdk.

    Returns {contract_sym: price} where price is:
      - last_price if valid (non-NaN, > 0)
      - ask_price1 if last_price unavailable
      - bid_price1 if ask_price1 also unavailable
      - None if no valid price found

    Returns all-None dict if TQ_USERNAME/TQ_PASSWORD not set or on any error.
    The caller should fall back to local file lookup for None entries.
    """
    import os

    username = os.environ.get("TQ_USERNAME", "")
    password = os.environ.get("TQ_PASSWORD", "")
    if not username or not password:
        return {s: None for s in contract_syms}

    try:
        import math
        import time

        from tqsdk import TqApi, TqAuth

        tq_syms = [_ag_to_tqsdk(s) for s in contract_syms]
        sym_map = dict(zip(tq_syms, contract_syms))  # tqsdk_sym → internal_sym

        api = TqApi(auth=TqAuth(username, password))
        quotes = {tq: api.get_quote(tq) for tq in tq_syms}

        # Wait up to timeout_sec for at least one quote to arrive
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            api.wait_update(deadline=min(time.time() + 3, deadline))
            # Check if we have any valid prices
            if any(
                q.last_price and math.isfinite(q.last_price) and q.last_price > 0
                for q in quotes.values()
            ):
                break

        result = {}
        for tq_sym, quote in quotes.items():
            internal = sym_map[tq_sym]
            price = None
            for attr in ("last_price", "ask_price1", "bid_price1"):
                v = getattr(quote, attr, None)
                if v is not None and math.isfinite(v) and v > 0:
                    price = float(v)
                    break
            result[internal] = price

        api.close()
        return result
    except Exception:
        return {s: None for s in contract_syms}
