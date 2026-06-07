"""Exchange-calendar helpers built on `exchange_calendars` (architecture
v0.3 §6.1 calendar awareness, §14.2 decision).

Why this module: timestamp-aware predicates like "is this weekly bar
truly closed at cutoff_ts" can't be done with `pd.Timedelta` arithmetic
alone (DST, US early closes, CN spring festival, CN futures night
sessions all violate naive 24h-day assumptions). We delegate to
`exchange_calendars` and only own the project's specific predicates.

Supported:
  - XNYS   — NYSE / US equities (full early-close + DST coverage)
  - XSHG   — Shanghai Stock Exchange (CN A-shares)
  - XSGE   — Shanghai Futures Exchange (au, ag, cu, rb)            [Step 0.5]
  - XDCE   — Dalian Commodity Exchange (m, i, j, jm, p, y)         [Step 0.5]
  - XZCE   — Zhengzhou Commodity Exchange (cf, ma, sr, ta)         [Step 0.5]
  - XINE   — Shanghai International Energy Exchange (sc)           [Step 0.5]
  - XCFE   — China Financial Futures Exchange (ic, if, ih, im)     [Step 0.5]

CN futures modeling decision (Step 0.5 — architecture v0.3 §14.2):
  We model only the *day session* (09:00/09:30 → 15:00 CST) as the
  exchange-level session, inheriting holidays from XSHG. `session_close`
  returns the day-session close (15:00 CST = 07:00 UTC), which is the
  canonical "trading-day close" used for daily bar completion.

  Night sessions (e.g. SHFE au/ag/cu/sc 21:00→02:30 next day, SHFE rb /
  DCE / CZCE 21:00→23:00 or 23:30) are NOT modeled as additional
  `exchange_calendars` sessions because the library supports only one
  break per session and the night-session close varies *per contract
  class*, not per exchange (e.g. SHFE au vs rb differ by 3.5 hours).
  Modeling each as its own calendar would force a combinatorial
  explosion (XSGE_metals, XSGE_steel, XSGE_base, ...) that the loader
  layer doesn't need: night-session intraday bars are stamped at their
  period_end and `is_bar_completed_at` is a pure temporal predicate
  (bar_period_end <= cutoff_ts), so per-contract precision is handled
  at the stamping layer, not here.

  Trade-off: `previous_session_close` only walks day-session closes.
  Callers that need night-session boundaries (rare; only relevant if a
  detector wants to "snap" intraday cutoffs to the most recent
  night-close) must use the contract-class-aware `NIGHT_SESSION_CLOSES`
  table directly. Documented as deferred; revisit if any detector
  actually requests it.

  Lunch-break simplification: SHFE/DCE/CZCE/INE commodity day sessions
  historically had two breaks (e.g. 10:15–10:30 + 11:30–13:30). We
  model only the main lunch break (11:30 → 13:30) because the small
  intra-morning break is irrelevant for daily-bar completeness and the
  library supports only one break per session. CFFEX uses 11:30 → 13:00
  with a 09:30 open (no second break).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from functools import lru_cache
from typing import Literal
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
from exchange_calendars.exchange_calendar_xshg import XSHGExchangeCalendar

Level = Literal["D", "W", "1h", "15m", "5m"]

# Patch tag stamped into CalendarVersion for CN futures exchanges. Bump
# the version suffix if night-session policy or lunch-break modeling
# changes — manifest caches must invalidate on this string changing
# (architecture v0.3 §6.3 + antipattern #18).
_CN_NIGHT_SESSION_PATCH = "cn_night_session_v1"

# CN futures exchanges (Step 0.5 — registered below via subclasses of
# XSHGExchangeCalendar). Each shares XSHG's holiday list.
_CN_FUTURES_EXCHANGES: set[str] = {"XSGE", "XDCE", "XZCE", "XINE", "XCFE"}

# Per-exchange canonical night-session close (latest close time of the
# night session, in the exchange's local tz). None means no night
# session. NB: these are *exchange-level* approximations — actual
# contract policy varies (SHFE au/cu/ag/sc go to 02:30 next day; SHFE
# rb stops at 23:00; DCE all our symbols stop at 23:30; CZCE stops at
# 23:00). We pick the LATEST close per exchange so the canonical close
# is an upper bound; callers needing per-contract precision should
# stamp at the loader layer.
NIGHT_SESSION_CLOSES: dict[str, time | None] = {
    # Upper-bound night close per exchange. Verified against TqSdk's
    # `night_trading_table` (authoritative source, 2026-05-28):
    #   SHFE au/ag : 21:00 → 02:30 next day
    #   SHFE sc    : 21:00 → 02:30 next day   (technically INE)
    #   SHFE cu    : 21:00 → 01:00 next day   (subsumed by XSGE 02:30 upper bound)
    #   SHFE rb    : 21:00 → 23:00            (subsumed by XSGE 02:30 upper bound)
    #   DCE all our symbols (m/i/j/jm/p/y) : 21:00 → 23:00
    #   CZCE all our symbols (cf/ma/sr/ta) : 21:00 → 23:00
    #   INE sc     : 21:00 → 02:30 next day
    #   CFFEX      : no night session
    "XSGE": time(2, 30),   # SHFE — au/ag/cu (cu actually 01:00; this is upper bound)
    "XDCE": time(23, 0),   # DCE  — all our symbols stop at 23:00 per TqSdk table
    "XZCE": time(23, 0),   # CZCE — cf/ma/sr/ta close 23:00
    "XINE": time(2, 30),   # INE  — sc closes 02:30 next day
    "XCFE": None,          # CFFEX — no night session
}

# Exchanges supported by this module. Add more here only after writing
# the corresponding calendar_edges tests.
SUPPORTED_EXCHANGES: set[str] = {"XNYS", "XSHG"} | _CN_FUTURES_EXCHANGES

# Exchanges we know we don't yet support but that callers might
# plausibly ask for. Empty now that all CN futures are patched in
# (Step 0.5). Kept as an explicit set so the error path can still
# differentiate "asked for a known-deferred exchange" from "asked for
# something completely unknown".
KNOWN_UNSUPPORTED_EXCHANGES: set[str] = set()


class CalendarNotSupportedError(NotImplementedError):
    """Raised when a caller asks for an exchange this module doesn't yet
    support. The message includes the planned patch step so the failure
    mode points at the design doc rather than at silent fallback."""


@dataclass(frozen=True)
class CalendarVersion:
    """The full version string we stamp into BarFrame.calendar_version.

    Includes the library version AND any local patches applied — so an
    artifact written with night-session patches stays distinguishable
    from one written without (manifest cache must invalidate on this
    string changing; architecture v0.3 §6.3 + antipattern #18).
    """

    exchange: str
    library_version: str   # e.g. "4.13.2"
    patches: tuple[str, ...] = ()  # e.g. ("cn_night_session_v1",)

    def __str__(self) -> str:
        base = f"exchange_calendars=={self.library_version}+{self.exchange}"
        if self.patches:
            base += "+" + "+".join(self.patches)
        return base


def _xcals_version() -> str:
    return xcals.__version__


# ---------------------------------------------------------------------------
# CN futures calendar subclasses (Step 0.5)
# ---------------------------------------------------------------------------
# Pattern: each CN futures exchange subclasses XSHGExchangeCalendar so
# it inherits the precomputed CN holiday list (1991→2026) plus
# bound_min/max. Only `name`, day-session open, and lunch-break are
# overridden. Holiday policy: CN futures exchanges historically observe
# the same statutory holidays as A-shares; minor 1-day discrepancies
# (e.g. extra dragon-boat make-up trading days) are below the resolution
# we care about for bar-completeness logic.


class _CNCommodityFuturesCalendar(XSHGExchangeCalendar):
    """SHFE/DCE/CZCE/INE day-session model.

    Day session: 09:00 → 15:00 CST with a lunch break 11:30 → 13:30.
    Inherits XSHG holiday calendar.
    """

    tz = ZoneInfo("Asia/Shanghai")
    open_times = ((None, time(9, 0)),)
    break_start_times = ((None, time(11, 30)),)
    break_end_times = ((None, time(13, 30)),)
    close_times = ((None, time(15, 0)),)


class XSGEExchangeCalendar(_CNCommodityFuturesCalendar):
    """Shanghai Futures Exchange — au, ag, cu, rb."""
    name = "XSGE"


class XDCEExchangeCalendar(_CNCommodityFuturesCalendar):
    """Dalian Commodity Exchange — m, i, j, jm, p, y."""
    name = "XDCE"


class XZCEExchangeCalendar(_CNCommodityFuturesCalendar):
    """Zhengzhou Commodity Exchange — cf, ma, sr, ta."""
    name = "XZCE"


class XINEExchangeCalendar(_CNCommodityFuturesCalendar):
    """Shanghai International Energy Exchange — sc."""
    name = "XINE"


class XCFEExchangeCalendar(XSHGExchangeCalendar):
    """China Financial Futures Exchange — ic, if, ih, im.

    Day session: 09:30 → 15:00 CST with lunch break 11:30 → 13:00.
    No night session. Inherits XSHG holiday calendar.
    """
    name = "XCFE"
    tz = ZoneInfo("Asia/Shanghai")
    open_times = ((None, time(9, 30)),)
    break_start_times = ((None, time(11, 30)),)
    break_end_times = ((None, time(13, 0)),)
    close_times = ((None, time(15, 0)),)


def _register_cn_futures_calendars() -> None:
    """Register CN futures calendar subclasses with exchange_calendars.

    Idempotent: re-registration on module reload (e.g. pytest with
    --forked) is a no-op rather than an error.
    """
    dispatcher = xcals.calendar_utils.global_calendar_dispatcher
    for name, cls in (
        ("XSGE", XSGEExchangeCalendar),
        ("XDCE", XDCEExchangeCalendar),
        ("XZCE", XZCEExchangeCalendar),
        ("XINE", XINEExchangeCalendar),
        ("XCFE", XCFEExchangeCalendar),
    ):
        if not dispatcher.has_calendar(name):
            xcals.register_calendar_type(name, cls)


_register_cn_futures_calendars()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def calendar_version_for(exchange: str) -> CalendarVersion:
    """Return the canonical CalendarVersion string for an exchange.

    CN futures exchanges include the `cn_night_session_v1` patch tag so
    artifacts written by them stay distinguishable from XSHG (whose
    holiday list they share) and from any future repatch.
    """
    if exchange not in SUPPORTED_EXCHANGES:
        if exchange in KNOWN_UNSUPPORTED_EXCHANGES:
            raise CalendarNotSupportedError(
                f"Exchange {exchange!r} is not yet supported. "
                f"See architecture v0.3 §14.2 for the deferred-work list."
            )
        raise CalendarNotSupportedError(
            f"Exchange {exchange!r} is not in SUPPORTED_EXCHANGES. "
            f"If you need it, add the corresponding edge-case tests to "
            f"tests/data/test_calendar_edges.py first."
        )
    patches: tuple[str, ...] = ()
    if exchange in _CN_FUTURES_EXCHANGES:
        patches = (_CN_NIGHT_SESSION_PATCH,)
    return CalendarVersion(
        exchange=exchange,
        library_version=_xcals_version(),
        patches=patches,
    )


def night_session_close(exchange: str) -> time | None:
    """Return the canonical night-session close time (local tz) for an
    exchange, or None if it has no night session.

    Exchange-level approximation: see module docstring for the per-
    contract caveats. Loaders needing exact per-contract semantics
    should not rely on this — stamp at the loader layer instead.
    """
    if exchange not in SUPPORTED_EXCHANGES:
        calendar_version_for(exchange)  # raises
    return NIGHT_SESSION_CLOSES.get(exchange)


@lru_cache(maxsize=16)
def _get_calendar(exchange: str) -> xcals.ExchangeCalendar:
    if exchange not in SUPPORTED_EXCHANGES:
        # Repeat the check so direct callers also fail loudly.
        calendar_version_for(exchange)  # raises
    return xcals.get_calendar(exchange)


def session_close(exchange: str, session_date: datetime) -> datetime:
    """Return the UTC close timestamp of the session containing `session_date`.

    For CN futures exchanges this is the *day-session* close (15:00 CST
    = 07:00 UTC), not the latest night-session close. See module
    docstring for the rationale.
    """
    cal = _get_calendar(exchange)
    # Coerce to date — exchange_calendars' session is keyed on date.
    if isinstance(session_date, datetime):
        date_key = session_date.date()
    else:
        date_key = session_date
    return cal.session_close(date_key).to_pydatetime()


def session_open(exchange: str, session_date: datetime) -> datetime:
    cal = _get_calendar(exchange)
    if isinstance(session_date, datetime):
        date_key = session_date.date()
    else:
        date_key = session_date
    return cal.session_open(date_key).to_pydatetime()


def is_session(exchange: str, session_date: datetime) -> bool:
    cal = _get_calendar(exchange)
    if isinstance(session_date, datetime):
        date_key = session_date.date()
    else:
        date_key = session_date
    return bool(cal.is_session(date_key))


def previous_session_close(exchange: str, ts: datetime) -> datetime:
    """The close timestamp of the most-recent FULLY CLOSED session at or
    before `ts`. If `ts` falls exactly on a session close, that close is
    returned (i.e. the bar IS knowable at `ts`)."""
    cal = _get_calendar(exchange)
    if ts.tzinfo is None:
        raise ValueError("ts must be tz-aware; pass a UTC datetime")

    # Codex P2 (2026-05-28 round 6): convert to UTC before deriving the
    # calendar date. A tz-aware non-UTC cutoff (e.g. ET 23:00 = next
    # day's 04:00 UTC) would otherwise start the search from the local
    # date and return a one-session-stale result.
    from datetime import timedelta
    from datetime import timezone as _tz
    ts_utc = ts.astimezone(_tz.utc)

    # Walk back through sessions; first one whose close <= ts wins.
    current = ts_utc.date()
    for _ in range(60):  # 60-session safety cap (covers CNY closure)
        if cal.is_session(current):
            close = cal.session_close(current).to_pydatetime()
            if close <= ts:
                return close
        # Step one day back.
        current = current - timedelta(days=1)
    raise ValueError(
        f"No completed session found within 60 days before {ts!r} on {exchange}. "
        f"Is the calendar correct / is the date plausibly in-range?"
    )


def is_bar_completed_at(
    exchange: str,
    level: Level,
    bar_period_end: datetime,
    cutoff_ts: datetime,
) -> bool:
    """Predicate used by ForeignTFView.require_completed (Step 1).

    Returns True iff a bar whose period_end is `bar_period_end` is
    fully knowable at `cutoff_ts`. For our period_end stamping
    convention this is simply `bar_period_end <= cutoff_ts`, BUT the
    calendar awareness piece is that `bar_period_end` must itself
    correspond to a real session close — callers (loaders) are
    responsible for stamping the right value. This function only
    checks the temporal predicate.

    For CN futures night-session bars: `bar_period_end` is whatever
    timestamp the loader stamped (e.g. au 15min bar covering
    02:15→02:30 CST has period_end = 02:30 CST = 18:30 UTC of the
    PRIOR calendar day). This function compares those tz-aware
    timestamps directly, which is the correct semantics regardless of
    which trading-day-of-record the bar belongs to.

    Codex P2 (2026-05-28): validate exchange first so callers can't
    silently fall through to naive time arithmetic on an unsupported
    calendar (matches the module's guardrail intent for CN futures).
    """
    if bar_period_end.tzinfo is None or cutoff_ts.tzinfo is None:
        raise ValueError("both timestamps must be tz-aware")
    if exchange not in SUPPORTED_EXCHANGES:
        # Trigger CalendarNotSupportedError with the standard message.
        calendar_version_for(exchange)
    return bar_period_end <= cutoff_ts
