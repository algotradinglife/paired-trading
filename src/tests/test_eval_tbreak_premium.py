"""Unit tests for eval_tbreak_premium — 合约文件名解析、OTM 选择、单事件模拟。"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.eval_tbreak_premium import (  # noqa: E402
    SLIP_TICKS,
    STOP_FRAC,
    TICK_SIZE,
    parse_option_filename,
    select_otm_contracts,
    simulate_event,
)


# --- 文件名解析 ----------------------------------------------------------
def test_parse_option_filename_call():
    assert parse_option_filename("SHFE.ag2408C7000.parquet") == {
        "sym": "ag", "month": "2408", "cp": "C", "strike": 7000}


def test_parse_option_filename_put_and_cu_large_strike():
    assert parse_option_filename("SHFE.au2408P520.parquet")["strike"] == 520
    cu = parse_option_filename("SHFE.cu2607C100000.parquet")
    assert cu["sym"] == "cu" and cu["cp"] == "C" and cu["strike"] == 100000


def test_parse_option_filename_rejects_future():
    # 期货合约（无 C/P）不应被当作期权
    assert parse_option_filename("SHFE.ag2408.parquet") is None
    assert parse_option_filename("random.parquet") is None


# --- OTM 选择 ------------------------------------------------------------
def _make_chain(tmp_path: Path, sym: str, month: str, cp: str, strikes: list[int]) -> Path:
    """造一批假期权 parquet（仅文件名 + 最小 schema 用于 glob/解析）。"""
    d = tmp_path / "daily"
    d.mkdir(exist_ok=True)
    for k in strikes:
        df = pd.DataFrame({
            "datetime": pd.to_datetime(["2024-07-01"]),
            "open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0],
            "volume": [0.0], "turnover": [0.0], "open_interest": [0.0],
        })
        df.to_parquet(d / f"SHFE.{sym}{month}{cp}{k}.parquet")
    return d


def test_select_otm_put(tmp_path):
    d = _make_chain(tmp_path, "ag", "2408", "P", [6800, 6900, 7000, 7100, 7200])
    # 现价 7050 → put OTM = strike<7050: 最近的是 7000(rank1), 6900(rank2)
    got = select_otm_contracts("ag", "P", 7050.0, daily_dir=d)
    by_rank = {c["otm_rank"]: c["strike"] for c in got}
    assert by_rank == {1: 7000, 2: 6900}


def test_select_otm_call(tmp_path):
    d = _make_chain(tmp_path, "ag", "2408", "C", [6800, 6900, 7000, 7100, 7200])
    # 现价 7050 → call OTM = strike>7050: 最近的是 7100(rank1), 7200(rank2)
    got = select_otm_contracts("ag", "C", 7050.0, daily_dir=d)
    by_rank = {c["otm_rank"]: c["strike"] for c in got}
    assert by_rank == {1: 7100, 2: 7200}


# --- 单事件模拟 ----------------------------------------------------------
def _write_contract(tmp_path: Path, name: str, rows: list[dict]) -> Path:
    d = tmp_path / "daily"
    d.mkdir(exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_parquet(d / f"{name}.parquet")
    return d


def test_simulate_event_time_exit(tmp_path):
    # break_date=2024-07-01；入场次日开盘 100，价格平稳不触止损 → 第10日收盘出场。
    # 数据须跨 >= MIN_DTE_DAYS(30) 自然日才过覆盖检查，故造 30 个交易日。
    dates = pd.bdate_range("2024-07-02", periods=30)
    rows = [{"datetime": dt, "open": 100.0, "high": 110.0, "low": 90.0,
             "close": 105.0, "volume": 1.0, "turnover": 0.0, "open_interest": 0.0}
            for dt in dates]
    d = _write_contract(tmp_path, "SHFE.ag2412C7600", rows)
    # 现价 7050 → call OTM rank1 = 7600 存在；MIN_DTE 覆盖 OK（数据到 ~7月中）
    out = simulate_event("ag", "call", "2024-07-01", 7050.0, daily_dir=d)
    assert out["evaluated"] is True
    tick = TICK_SIZE["ag"]
    entry = 100.0 + SLIP_TICKS * tick
    exit_fill = 105.0 - SLIP_TICKS * tick
    assert out["exit_reason"] == "time"
    assert out["entry"] == pytest.approx(entry)
    assert out["exit"] == pytest.approx(exit_fill)
    assert out["multiple"] == pytest.approx(exit_fill / entry)


def test_simulate_event_stop_exit(tmp_path):
    # 第3日 low 跌破 entry*0.5 → 止损成交（数据跨 30 个交易日满足覆盖检查）
    dates = pd.bdate_range("2024-07-02", periods=30)
    rows = []
    for i, dt in enumerate(dates):
        low = 90.0 if i != 2 else 10.0  # 第3日深跌
        rows.append({"datetime": dt, "open": 100.0, "high": 110.0, "low": low,
                     "close": 105.0, "volume": 1.0, "turnover": 0.0,
                     "open_interest": 0.0})
    d = _write_contract(tmp_path, "SHFE.ag2412C7600", rows)
    out = simulate_event("ag", "call", "2024-07-01", 7050.0, daily_dir=d)
    tick = TICK_SIZE["ag"]
    entry = 100.0 + SLIP_TICKS * tick
    stop = entry * STOP_FRAC
    assert out["exit_reason"] == "stop"
    assert out["exit"] == pytest.approx(stop - SLIP_TICKS * tick)
    assert out["multiple"] < 0.5  # 被止损，倍数低


def test_simulate_event_skipped_when_no_option(tmp_path):
    d = tmp_path / "daily"
    d.mkdir()
    out = simulate_event("ag", "put", "2024-07-01", 7050.0, daily_dir=d)
    assert out["evaluated"] is False
    assert out["exit_reason"] == "skipped_no_option"
    assert out["multiple"] is None


def test_simulate_event_skipped_when_no_otm_in_live_month(tmp_path):
    # 现价 7465 的 put 事件：唯一覆盖足够的月份 strike 下限 7600（>现价→对 put 是 ITM），
    # 月内无 OTM put（strike<7465）→ 必须 skip，而非误选其他月的全局 OTM strike。
    dates = pd.bdate_range("2024-12-23", periods=30)
    rows = [{"datetime": dt, "open": 100.0, "high": 110.0, "low": 90.0,
             "close": 105.0, "volume": 1.0, "turnover": 0.0, "open_interest": 0.0}
            for dt in dates]
    d = tmp_path / "daily"
    d.mkdir()
    pd.DataFrame(rows).to_parquet(d / "SHFE.ag2505P7600.parquet")  # 唯一 put，ITM
    out = simulate_event("ag", "put", "2024-12-20", 7465.0, daily_dir=d)
    assert out["evaluated"] is False
    assert out["exit_reason"] == "skipped_no_option"


# --- v1 升级：≥14d 选月规则 / 多交易所 / folds / 网格 ----------------------
from datetime import date as _date  # noqa: E402

from scripts.eval_tbreak_premium import build_report  # noqa: E402


def _chain_rows(start: str, periods: int, open_=100.0, low=90.0, close=105.0):
    return [{"datetime": dt, "open": open_, "high": 110.0, "low": low,
             "close": close, "volume": 1.0, "turnover": 0.0, "open_interest": 0.0}
            for dt in pd.bdate_range(start, periods=periods)]


def test_pick_respects_14d_rule_rolls_dead_near_month(tmp_path):
    # ag2412 链已死（终止 2024-11-18，早于库内最新日期）；破位 2024-11-07
    # 距其真实到期仅 11 天 (<14) → 必须滚到 2501，即便 2412 仍有数据可入场。
    d = tmp_path / "daily"
    d.mkdir()
    dead = _chain_rows("2024-10-01", 35)            # ~2024-11-18 终止
    live = _chain_rows("2024-11-01", 40)            # 延伸到 12 月下旬（库内最新）
    pd.DataFrame(dead).to_parquet(d / "SHFE.ag2412C7600.parquet")
    pd.DataFrame(live).to_parquet(d / "SHFE.ag2501C7600.parquet")
    out = simulate_event("ag", "call", "2024-11-07", 7050.0, daily_dir=d)
    assert out["evaluated"] is True
    assert out["month"] == "2501"


def test_pick_handles_dce_dialect_put(tmp_path):
    d = tmp_path / "daily"
    d.mkdir()
    pd.DataFrame(_chain_rows("2024-11-08", 40)).to_parquet(
        d / "DCE.i2502-P-740.parquet")
    out = simulate_event("i", "put", "2024-11-07", 760.0, daily_dir=d)
    assert out["evaluated"] is True
    assert out["strike"] == 740 and out["month"] == "2502"


def test_build_report_has_folds_and_grid(tmp_path):
    d = tmp_path / "daily"
    d.mkdir()
    pd.DataFrame(_chain_rows("2024-11-08", 40)).to_parquet(
        d / "SHFE.ag2501C7600.parquet")
    pd.DataFrame(_chain_rows("2025-09-02", 40)).to_parquet(
        d / "SHFE.ag2511C7600.parquet")
    events = [
        {"symbol": "ag", "side": "call", "break_date": "2024-11-07",
         "break_close": 7050.0},
        {"symbol": "ag", "side": "call", "break_date": "2025-09-01",
         "break_close": 7050.0},
    ]
    rep = build_report(events, daily_dir=d, is_cutoff_date=_date(2025, 6, 30))
    assert rep["folds"]["is"]["n"] == 1 and rep["folds"]["oos"]["n"] == 1
    grid = rep["sensitivity_grid"]
    assert "stop0.5_hold10" in grid
    assert len(grid) >= 9
    for cell in grid.values():
        assert set(cell) >= {"n", "ev", "put_ev", "call_ev"}


# --- US lane：符号分流 / broad-market 排除（t_aa79fb13）-------------------
from scripts.eval_tbreak_premium import (  # noqa: E402
    US_EXCLUDED_BROAD_DEFENSIVE,
    check_us_exclusions,
    events_from_scan,
    fetch_events,
    split_symbols_by_lane,
)


def test_split_symbols_by_lane_mixed():
    cn, us = split_symbols_by_lane(["ag", "GLD", "cu", "GDX", "IWM"])
    assert cn == ["ag", "cu"]
    assert us == ["GLD", "GDX", "IWM"]


def test_split_symbols_by_lane_unknown_raises():
    # 小写但不在 POOL_KEY → 未知；混大小写也未知
    with pytest.raises(ValueError, match="未知符号"):
        split_symbols_by_lane(["zz"])
    with pytest.raises(ValueError, match="未知符号"):
        split_symbols_by_lane(["Gld"])
    # 大写但不在 scan US 池 → 未知（codex P2：防止合法零事件假象）
    with pytest.raises(ValueError, match="未知符号"):
        split_symbols_by_lane(["AAPL"])


def test_us_broad_defensive_excluded_by_default():
    assert {"SPY", "DIA", "XLU", "XLP", "XLV"} <= set(US_EXCLUDED_BROAD_DEFENSIVE)
    with pytest.raises(ValueError, match="SPY"):
        check_us_exclusions(["GLD", "SPY"], allow_excluded=False)
    # fetch_events 在跑 scan 之前就应拒绝（无 subprocess 即抛错）
    with pytest.raises(ValueError, match="--allow-excluded-us"):
        fetch_events(["SPY"], "2024-07-01")


def test_us_exclusion_optin_and_clean_symbols_pass():
    check_us_exclusions(["GLD", "GDX", "IWM", "NVDA"], allow_excluded=False)
    check_us_exclusions(["SPY"], allow_excluded=True)  # 冒烟显式放行


def test_events_from_scan_us_pool_keys_are_tickers():
    data = {"US": {"GLD": [
        {"candidate": "put_candidate", "break_date": "2025-01-06",
         "break_close": 240.5},
        {"candidate": "call_candidate", "break_date": "2025-03-03",
         "break_close": 265.0},
    ]}}
    got = events_from_scan(data, "US", {"GLD": "GLD"})
    assert [e["side"] for e in got] == ["put", "call"]
    assert got[0] == {"symbol": "GLD", "side": "put",
                      "break_date": "2025-01-06", "break_close": 240.5}


def test_events_from_scan_cn_pool_key_mapping():
    data = {"CN_COMMODITY": {"kq_m_shfe_ag": [
        {"candidate": "put_candidate", "break_date": "2024-08-01",
         "break_close": 7000.0},
    ]}}
    got = events_from_scan(data, "CN_COMMODITY", {"ag": "kq_m_shfe_ag"})
    assert got == [{"symbol": "ag", "side": "put",
                    "break_date": "2024-08-01", "break_close": 7000.0}]


def test_us_premium_path_pending_fails_loud(tmp_path):
    # seam（t_e7fb18c9）交付前 US 事件不得流入 CN 月规则选约（codex P2）
    from scripts.eval_tbreak_premium import pick_contract_for_event
    d = tmp_path / "daily"
    d.mkdir()
    with pytest.raises(NotImplementedError, match="t_e7fb18c9"):
        pick_contract_for_event("GLD", "P", "2025-01-06", 240.5, daily_dir=d)


def test_us_event_graceful_skip_in_report(tmp_path):
    # US 事件在 seam 交付前进 build_report 应被标记 skip，而非中断整批（codex P2）
    d = tmp_path / "daily"
    d.mkdir()
    pd.DataFrame(_chain_rows("2024-11-08", 40)).to_parquet(
        d / "SHFE.ag2501C7600.parquet")
    events = [
        {"symbol": "ag", "side": "call", "break_date": "2024-11-07",
         "break_close": 7050.0},
        {"symbol": "GLD", "side": "put", "break_date": "2024-11-07",
         "break_close": 240.5},
    ]
    rep = build_report(events, daily_dir=d, is_cutoff_date=_date(2025, 6, 30))
    assert rep["n_evaluated"] == 1
    assert rep["n_skipped_us_pending_seam"] == 1
    assert rep["n_skipped_no_option"] == 0
    us_row = next(e for e in rep["events"] if e["symbol"] == "GLD")
    assert us_row["evaluated"] is False
    assert us_row["exit_reason"] == "skipped_us_pending_seam"
