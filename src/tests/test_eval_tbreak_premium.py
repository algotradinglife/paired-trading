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
