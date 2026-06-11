"""OI/volume main-contract continuous synthesis (data/continuous.py).

Semantics under test:
  - discovery: prefix (``SHFE.cu2509``) and CZCE suffix (``CF509.CZCE``)
    filenames; same canonical month dedupes preferring the 4-digit form;
    option files never match.
  - metric: per-date open_interest when any active contract has OI > 0,
    volume otherwise (historical files carry OI = 0).
  - selection: decision for date d uses the PRIOR session's settlement
    metric (no lookahead); the first session bootstraps on itself.
  - roll: a challenger with a LATER expiry must beat the incumbent for
    ``confirm_days`` consecutive sessions; the switch is effective the
    next session. Earlier-expiry contracts never become main again
    (forward-only). An expired incumbent forces an immediate roll.
  - intraday: a contract's bars are sliced by trading day — night-session
    bars (period_end > 16:00, or <= 04:00 next calendar day) belong to
    the NEXT trading day.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

from data import continuous


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _bar(dt: datetime, px: float, vol: float, oi: float = 0.0) -> dict:
    return {
        "datetime": dt,
        "open": px, "high": px + 1, "low": px - 1, "close": px,
        "volume": vol, "turnover": px * vol, "open_interest": oi,
    }


def _write(root: Path, folder: str, name: str, bars: list[dict]) -> None:
    d = root / folder
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(bars).to_parquet(d / f"{name}.parquet", index=False)


D = [datetime(2025, 3, d) for d in (3, 4, 5, 6, 7)]  # Mon-Fri sessions


def _two_contract_store(tmp_path, vols_a, vols_b, ois_a=None, ois_b=None):
    """cu2504 (A) and cu2505 (B) with given per-day volumes/OI."""
    ois_a = ois_a or [0.0] * len(vols_a)
    ois_b = ois_b or [0.0] * len(vols_b)
    _write(tmp_path, "daily", "SHFE.cu2504",
           [_bar(D[i], 100 + i, vols_a[i], ois_a[i]) for i in range(len(vols_a))])
    _write(tmp_path, "daily", "SHFE.cu2505",
           [_bar(D[i], 200 + i, vols_b[i], ois_b[i]) for i in range(len(vols_b))])
    return tmp_path


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def test_discovery_excludes_options_and_dedupes_czce(tmp_path):
    _write(tmp_path, "daily", "CZCE.CF2509", [_bar(D[0], 100, 10)])
    _write(tmp_path, "daily", "CF509.CZCE", [_bar(D[0], 999, 10)])   # same month
    _write(tmp_path, "daily", "CZCE.CF2601", [_bar(D[0], 100, 5)])
    _write(tmp_path, "daily", "CZCE.CF509C13000", [_bar(D[0], 1, 1)])  # option
    found = continuous.discover_contracts(tmp_path, "daily", "CZCE", "CF")
    assert sorted(found.keys()) == ["202509", "202601"]
    assert found["202509"].name == "CZCE.CF2509.parquet"  # 4-digit preferred


def test_discovery_shfe_excludes_strike_suffixed_options(tmp_path):
    _write(tmp_path, "daily", "SHFE.cu2504", [_bar(D[0], 100, 10)])
    _write(tmp_path, "daily", "SHFE.cu2504C78000", [_bar(D[0], 1, 1)])
    found = continuous.discover_contracts(tmp_path, "daily", "SHFE", "cu")
    assert sorted(found.keys()) == ["202504"]


# ---------------------------------------------------------------------------
# Schedule / roll
# ---------------------------------------------------------------------------

def test_bootstrap_picks_max_metric_first_session(tmp_path):
    _two_contract_store(tmp_path, vols_a=[90, 90, 90, 90, 90], vols_b=[10, 10, 10, 10, 10])
    sched = continuous.build_main_schedule(tmp_path, "SHFE", "cu", confirm_days=2)
    assert sched[date(2025, 3, 3)] == "202504"


def test_partial_oi_coverage_falls_back_to_volume(tmp_path):
    # Mid-backfill state: a far month was re-synced WITH OI while the true
    # main still carries OI=0. OI must only be trusted when ALL active
    # contracts have it; otherwise the freshly-synced far month would
    # hijack the schedule.
    _two_contract_store(
        tmp_path,
        vols_a=[90] * 5, vols_b=[10] * 5,   # A is the real main by volume
        ois_a=[0.0] * 5, ois_b=[800.0] * 5,  # only B re-synced with OI
    )
    sched = continuous.build_main_schedule(tmp_path, "SHFE", "cu", confirm_days=2)
    assert sched[date(2025, 3, 3)] == "202504"   # volume rules; B does not hijack
    assert sched[date(2025, 3, 7)] == "202504"


def test_oi_preferred_over_volume_when_present(tmp_path):
    # B dominates volume but A dominates OI -> A is main
    _two_contract_store(
        tmp_path,
        vols_a=[10] * 5, vols_b=[90] * 5,
        ois_a=[5000] * 5, ois_b=[1000] * 5,
    )
    sched = continuous.build_main_schedule(tmp_path, "SHFE", "cu", confirm_days=2)
    assert sched[date(2025, 3, 3)] == "202504"


def test_roll_requires_consecutive_confirmation(tmp_path):
    # B first beats A at the day3 settlement and stays ahead on day4:
    # streak reaches confirm_days=2 at the day4 settlement -> switch
    # effective day5. Decisions always use the PRIOR session's metric.
    _two_contract_store(
        tmp_path,
        vols_a=[90, 50, 40, 40, 40],
        vols_b=[10, 30, 70, 70, 70],
    )
    sched = continuous.build_main_schedule(tmp_path, "SHFE", "cu", confirm_days=2)
    assert sched[date(2025, 3, 4)] == "202504"   # day1 bootstrap A
    assert sched[date(2025, 3, 5)] == "202504"   # B still behind at day2
    assert sched[date(2025, 3, 6)] == "202504"   # streak=1 (day3 settle)
    assert sched[date(2025, 3, 7)] == "202505"   # streak=2 -> switch


def test_brief_backward_spike_does_not_switch(tmp_path):
    # main is B (later month); A (earlier) spikes for ONE day only ->
    # confirmation absorbs it, stays B
    _two_contract_store(
        tmp_path,
        vols_a=[10, 99, 20, 20, 20],
        vols_b=[90, 80, 80, 80, 80],
    )
    sched = continuous.build_main_schedule(tmp_path, "SHFE", "cu", confirm_days=2)
    assert sched[date(2025, 3, 3)] == "202505"
    assert sched[date(2025, 3, 7)] == "202505"


def test_sustained_flip_recovers_even_backward(tmp_path):
    # Self-healing over the forward-only ratchet: when the schedule lands
    # on a far month (junk-era artifact / mid-backfill store) and an
    # EARLIER month is persistently dominant, the schedule must recover —
    # a hard forward-only ratchet would lock out the true main forever.
    _two_contract_store(
        tmp_path,
        vols_a=[10, 95, 95, 95, 95],   # A = earlier month, true main
        vols_b=[90, 20, 20, 20, 20],   # B briefly looked dominant on day1
    )
    sched = continuous.build_main_schedule(tmp_path, "SHFE", "cu", confirm_days=2)
    assert sched[date(2025, 3, 3)] == "202505"   # bootstrap on day1 data
    assert sched[date(2025, 3, 7)] == "202504"   # recovered to the true main


def test_expired_incumbent_forces_roll(tmp_path):
    # A has bars only on day1-2 (expires), B continues
    _write(tmp_path, "daily", "SHFE.cu2504",
           [_bar(D[0], 100, 90), _bar(D[1], 101, 90)])
    _write(tmp_path, "daily", "SHFE.cu2505",
           [_bar(D[i], 200 + i, 10) for i in range(5)])
    sched = continuous.build_main_schedule(tmp_path, "SHFE", "cu", confirm_days=5)
    assert sched[date(2025, 3, 4)] == "202504"
    assert sched[date(2025, 3, 5)] == "202505"   # forced despite confirm_days=5


# ---------------------------------------------------------------------------
# Series synthesis
# ---------------------------------------------------------------------------

def test_daily_series_stitches_prices_per_segment(tmp_path):
    _two_contract_store(
        tmp_path,
        vols_a=[90, 90, 40, 40, 40],
        vols_b=[10, 95, 95, 70, 70],
    )
    df = continuous.synthesize_continuous(tmp_path, "SHFE", "cu", "D", confirm_days=2)
    # bootstrap A; B exceeds on day2+day3 -> switch effective day4
    closes = dict(zip(df["datetime"].dt.date, df["close"]))
    assert closes[date(2025, 3, 3)] == 100   # A
    assert closes[date(2025, 3, 6)] == 203   # B
    assert list(df.columns) == [
        "datetime", "open", "high", "low", "close",
        "volume", "turnover", "open_interest",
    ]


def test_intraday_night_bars_belong_to_next_trading_day(tmp_path):
    # Schedule: Mon+Tue main=A, roll effective Wed (B beats A at the Tue
    # settlement, confirm_days=1). Tuesday's NIGHT session (Tue 21:00+ and
    # Wed 01:00 ends) is part of trading day WED and must come from B.
    _write(tmp_path, "daily", "SHFE.cu2504", [
        _bar(datetime(2025, 3, 3), 100, 90),
        _bar(datetime(2025, 3, 4), 101, 50),
        _bar(datetime(2025, 3, 5), 102, 10),
    ])
    _write(tmp_path, "daily", "SHFE.cu2505", [
        _bar(datetime(2025, 3, 3), 200, 10),
        _bar(datetime(2025, 3, 4), 201, 80),
        _bar(datetime(2025, 3, 5), 202, 95),
    ])
    _write(tmp_path, "hour", "SHFE.cu2504", [
        _bar(datetime(2025, 3, 4, 15, 0), 100, 5),   # Tue day -> Tue (A)
        _bar(datetime(2025, 3, 4, 22, 0), 100, 5),   # Tue night -> Wed (drop)
        _bar(datetime(2025, 3, 5, 15, 0), 101, 5),   # Wed day (drop)
    ])
    _write(tmp_path, "hour", "SHFE.cu2505", [
        _bar(datetime(2025, 3, 4, 15, 0), 200, 5),   # Tue day (drop)
        _bar(datetime(2025, 3, 4, 22, 0), 200, 5),   # Tue night -> Wed (B)
        _bar(datetime(2025, 3, 5, 1, 0), 200.5, 5),  # Tue night cont. -> Wed (B)
        _bar(datetime(2025, 3, 5, 15, 0), 201, 5),   # Wed day (B)
    ])
    df = continuous.synthesize_continuous(tmp_path, "SHFE", "cu", "60min", confirm_days=1)
    got = list(zip(df["datetime"], df["close"]))
    assert got == [
        (datetime(2025, 3, 4, 15, 0), 100.0),
        (datetime(2025, 3, 4, 22, 0), 200.0),
        (datetime(2025, 3, 5, 1, 0), 200.5),
        (datetime(2025, 3, 5, 15, 0), 201.0),
    ]


def test_weekly_resample_from_daily(tmp_path):
    _two_contract_store(tmp_path, vols_a=[90] * 5, vols_b=[10] * 5)
    df = continuous.synthesize_continuous(tmp_path, "SHFE", "cu", "W", confirm_days=2)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["datetime"] == datetime(2025, 3, 7)   # last session of the week
    assert row["open"] == 100 and row["close"] == 104
    assert row["high"] == 105 and row["low"] == 99
    assert row["volume"] == 450


def test_placeholder_rows_with_zero_prices_dropped(tmp_path):
    # Far-month files carry close-only placeholder rows (OHLV = 0).
    bars = [_bar(D[i], 100 + i, 90) for i in range(5)]
    bars[2] = {
        "datetime": D[2], "open": 0.0, "high": 0.0, "low": 0.0,
        "close": 68940.0, "volume": 0.0, "turnover": 0.0, "open_interest": 0.0,
    }
    _write(tmp_path, "daily", "SHFE.cu2504", bars)
    _write(tmp_path, "daily", "SHFE.cu2505",
           [_bar(D[i], 200 + i, 10) for i in range(5)])
    df = continuous.synthesize_continuous(tmp_path, "SHFE", "cu", "D", confirm_days=2)
    assert date(2025, 3, 5) not in set(df["datetime"].dt.date)
    assert (df[["open", "high", "low", "close"]] > 0).all().all()


def test_illiquid_head_trimmed(tmp_path):
    # Real main contracts are missing early on; the only candidate is an
    # illiquid far month (vol 1 vs the liquid regime's 1000). The
    # synthesized series must start when real liquidity appears.
    days = [datetime(2025, 3, d) for d in (3, 4, 5, 6, 7, 10, 11, 12, 13, 14)]
    _write(tmp_path, "daily", "SHFE.cu2504",
           [_bar(days[i], 100 + i, 1.0) for i in range(3)] +
           [_bar(days[i], 100 + i, 1000.0) for i in range(3, 10)])
    df = continuous.synthesize_continuous(tmp_path, "SHFE", "cu", "D", confirm_days=2)
    assert df["datetime"].dt.date.iloc[0] == date(2025, 3, 6)
    assert len(df) == 7


def test_illiquid_head_trim_applies_to_intraday(tmp_path):
    days = [datetime(2025, 3, d) for d in (3, 4, 5, 6, 7, 10, 11, 12, 13, 14)]
    _write(tmp_path, "daily", "SHFE.cu2504",
           [_bar(days[i], 100 + i, 1.0) for i in range(3)] +
           [_bar(days[i], 100 + i, 1000.0) for i in range(3, 10)])
    _write(tmp_path, "hour", "SHFE.cu2504", [
        _bar(datetime(2025, 3, 4, 15, 0), 100, 1),     # trimmed head
        _bar(datetime(2025, 3, 6, 15, 0), 103, 500),   # kept
    ])
    df = continuous.synthesize_continuous(tmp_path, "SHFE", "cu", "60min", confirm_days=2)
    assert list(df["datetime"]) == [datetime(2025, 3, 6, 15, 0)]


def test_trimmed_head_night_bars_not_remapped_into_series(tmp_path):
    # Night bars from TRIMMED head dates must not bisect onto the first
    # post-trim session and leak back into the series.
    days = [datetime(2025, 3, d) for d in (3, 4, 5, 6, 7, 10, 11, 12, 13, 14)]
    _write(tmp_path, "daily", "SHFE.cu2504",
           [_bar(days[i], 100 + i, 1.0) for i in range(3)] +
           [_bar(days[i], 100 + i, 1000.0) for i in range(3, 10)])
    _write(tmp_path, "hour", "SHFE.cu2504", [
        # night bar of trading day 3/4 (trimmed) — must NOT remap to 3/6
        _bar(datetime(2025, 3, 3, 22, 0), 100, 1),
        # night bar of trading day 3/7 (kept)
        _bar(datetime(2025, 3, 6, 22, 0), 103, 500),
        _bar(datetime(2025, 3, 6, 15, 0), 103, 500),
    ])
    df = continuous.synthesize_continuous(tmp_path, "SHFE", "cu", "60min", confirm_days=2)
    assert list(df["datetime"]) == [
        datetime(2025, 3, 6, 15, 0),
        datetime(2025, 3, 6, 22, 0),
    ]


# ---------------------------------------------------------------------------
# BarStore integration
# ---------------------------------------------------------------------------

def test_barstore_synthesizes_continuous_for_zero_suffix(tmp_path):
    from data.store import BarStore
    from datetime import timezone
    _two_contract_store(tmp_path, vols_a=[90] * 5, vols_b=[10] * 5)
    bf = BarStore(tmp_path).load_barframe(
        "cu0", "XSHF", "D",
        as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert len(bf.df) == 5
    assert bf.df["close"].iloc[0] == 100.0
    assert str(bf.df["timestamp"].iloc[0]) == "2025-03-03 00:00:00+00:00"


def test_barstore_prefers_real_continuous_file_with_longer_coverage(tmp_path):
    # Provider continuous file covering MORE sessions than synthesis wins.
    from data.store import BarStore
    from datetime import timezone
    _two_contract_store(tmp_path, vols_a=[90] * 5, vols_b=[10] * 5)  # 5 sessions
    extra = [datetime(2025, 2, d) for d in (24, 25, 26)]
    _write(tmp_path, "daily", "SHFE.cu0",
           [_bar(dt, 555, 1) for dt in extra] + [_bar(d, 555, 1) for d in D])
    bf = BarStore(tmp_path).load_barframe(
        "cu0", "XSHF", "D",
        as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert len(bf.df) == 8
    assert bf.df["close"].iloc[0] == 555.0


def test_barstore_synthesis_wins_over_stub_continuous_file(tmp_path):
    # Mid-backfill: the pipeline may have created a continuous file with
    # only a few recent rows. Synthesis from contract months covers more
    # sessions and must win until the provider file catches up.
    from data.store import BarStore
    from datetime import timezone
    _two_contract_store(tmp_path, vols_a=[90] * 5, vols_b=[10] * 5)  # 5 sessions
    _write(tmp_path, "daily", "SHFE.cu0", [_bar(D[4], 555, 1)])      # 1-row stub
    bf = BarStore(tmp_path).load_barframe(
        "cu0", "XSHF", "D",
        as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert len(bf.df) == 5
    assert bf.df["close"].iloc[0] == 100.0   # synthesized series
