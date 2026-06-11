"""eval_tbreak_premium.py — Phase A 链事件权利金空间评估（trade-philosopher 首圈）。

机械评估器：只输出统计，**不打 PASS/FAIL，不解读**。裁决在另一个 session。

事件来源
--------
内部 subprocess 跑 scripts/scan_tbreak_chain.py --pool CN_COMMODITY 落临时 JSON，
再按 --symbols / --since 过滤到 SHFE ag/au/cu/rb（POOL key kq_m_shfe_<sym>）。
每事件携带 symbol / candidate(put_candidate|call_candidate) / break_date / break_close。

合约选择（每事件）
----------------
- 方向：put_candidate → put（P），call_candidate → call（C）。
- 浅虚 1-2 档 OTM：put 选 strike < break_close，call 选 strike > break_close，
  取距现价最近的 1 档（OTM rank 1）；若该档无数据则退到 rank 2。
- 到期月：从 break_date 起，数据覆盖延伸 >= 30 自然日（MIN_DTE_DAYS）的**最近**合约月，
  且合约在破位时已上市（入场日须在 break_date 后 <= MAX_ENTRY_GAP_DAYS=7 自然日内，
  排除数据从晚期才开始的远月合约造成的数百天错配）。
- strike / 月份 / CP 从 quant_data daily parquet 文件名解析：SHFE.<sym><YYMM><C|P><strike>.parquet
  （strike 在文件名里均为整数，au 实测无小数点位）。

入场 / 出场 / 风险几何（写死，输出到 JSON 的 params）
------------------------------------------------
- 入场：break_date 次一交易日（option 自身 datetime 序列里 > break_date 的首个日）的 open。
  该日无数据 / 期权文件缺失 → 事件记 skipped_no_option，单独计数，不进 EV。
- 止损：stop_price = entry_premium * STOP_FRAC（0.5，权利金腰斩出局，肖式小止损日线粒度保守版）。
  持有期内某日 low <= stop_price → 当日以 stop_price 成交（被止损）。
- 时间止损：第 HOLD_DAYS（10）个交易日（含入场日为第1日往后数）收盘价出场。
- 数据断档：持有期内 option 数据提前结束 → 以最后可用收盘价出场（exit_reason=data_gap）。
- 滑点：无 bid/ask。入场 +SLIP_TICKS（2）不利（买价更高），出场 -SLIP_TICKS 不利（卖价更低）。

倍数 / EV
--------
premium_multiple = exit_fill / entry_fill；EV = mean(multiple)。
bootstrap 95% CI：10000 次，numpy seed=42。逐方向（put/call）、逐品种分解。

Tick size（实测自合约价格序列最小非零增量，2026-06-11；cu 实测=2.0 非传闻的10）：
  ag=0.5  au=0.02  cu=2.0  rb=0.5

Usage:
  uv run python scripts/eval_tbreak_premium.py --symbols ag,au,cu,rb --since 2024-07-01 \
      --out /path/to/premium_eval.json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

SRC_DIR = Path(__file__).resolve().parents[1]
DAILY_DIR = SRC_DIR / "data" / "quant" / "daily"
SCAN_SCRIPT = SRC_DIR / "scripts" / "scan_tbreak_chain.py"

# --- 风险几何 / 滑点 参数（写死，输出到 JSON params）------------------------
STOP_FRAC = 0.5        # 止损 = 入场权利金 * 0.5（腰斩出局）
HOLD_DAYS = 10         # 时间止损：第 10 个交易日收盘出场
SLIP_TICKS = 2         # 入出各 2 tick 不利滑点
MIN_DTE_DAYS = 30      # 到期月须距 break_date >= 30 自然日（用数据覆盖延伸近似）
MAX_ENTRY_GAP_DAYS = 7  # 入场日须在 break_date 后 <= 7 自然日内（确保是真·次一交易日、
                        # 合约在破位时已上市；否则远月合约数据从晚期才开始会造成数百天错配）
OTM_MAX_RANK = 2       # 浅虚最多取到第 2 档
BOOTSTRAP_N = 10000
BOOTSTRAP_SEED = 42

# Tick size（实测，见 docstring）
TICK_SIZE: dict[str, float] = {"ag": 0.5, "au": 0.02, "cu": 2.0, "rb": 0.5}

# scan POOL key（kq_m_shfe_<sym>）-> 短代码
POOL_KEY = {"ag": "kq_m_shfe_ag", "au": "kq_m_shfe_au",
            "cu": "kq_m_shfe_cu", "rb": "kq_m_shfe_rb"}

# 文件名：SHFE.<sym><YYMM><C|P><strike>.parquet
_OPT_RE = re.compile(r"^SHFE\.(?P<sym>[a-z]{2})(?P<month>\d{4})(?P<cp>[CP])(?P<strike>\d+)\.parquet$")


# ---------------------------------------------------------------------------
# 文件名解析 / 合约枚举（纯函数，可单测）
# ---------------------------------------------------------------------------
def parse_option_filename(name: str) -> dict | None:
    """解析期权 parquet 文件名 -> {sym, month, cp, strike}；非期权返回 None。

    >>> parse_option_filename("SHFE.ag2408C7000.parquet")
    {'sym': 'ag', 'month': '2408', 'cp': 'C', 'strike': 7000}
    >>> parse_option_filename("SHFE.au2408P520.parquet")['strike']
    520
    >>> parse_option_filename("SHFE.ag2408.parquet")  # 期货，非期权
    >>> parse_option_filename("SHFE.cu2607C100000.parquet")['strike']
    100000
    """
    m = _OPT_RE.match(name)
    if m is None:
        return None
    return {
        "sym": m.group("sym"),
        "month": m.group("month"),
        "cp": m.group("cp"),
        "strike": int(m.group("strike")),
    }


def list_option_contracts(sym: str, cp: str, daily_dir: Path = DAILY_DIR) -> list[dict]:
    """列出某品种某方向的全部期权合约（解析自文件名），按 (month, strike) 排序。"""
    out: list[dict] = []
    for p in sorted(daily_dir.glob(f"SHFE.{sym}*{cp}*.parquet")):
        info = parse_option_filename(p.name)
        if info is None or info["sym"] != sym or info["cp"] != cp:
            continue
        info["path"] = p
        out.append(info)
    out.sort(key=lambda d: (d["month"], d["strike"]))
    return out


def _yymm_to_expiry_floor(month: str) -> pd.Timestamp:
    """合约月 YYMM -> 该交割月 1 号（粗略，仅用于排序参考；实际 DTE 用数据覆盖判断）。"""
    yy, mm = int(month[:2]), int(month[2:])
    return pd.Timestamp(year=2000 + yy, month=mm, day=1)


def _rank_otm_strikes(strikes: list[int], cp: str, underlying_px: float) -> dict[int, int]:
    """给定一组 strike，返回 {strike: otm_rank}（1=最浅虚），最多 OTM_MAX_RANK 档。

    put：strike < 现价（降序，最近现价者 rank1）；call：strike > 现价（升序）。
    """
    uniq = sorted(set(strikes))
    if cp == "P":
        otm = sorted((k for k in uniq if k < underlying_px), reverse=True)
    else:
        otm = sorted(k for k in uniq if k > underlying_px)
    return {k: i + 1 for i, k in enumerate(otm[:OTM_MAX_RANK])}


def select_otm_contracts(sym: str, cp: str, underlying_px: float,
                         daily_dir: Path = DAILY_DIR) -> list[dict]:
    """按现价选浅虚 1-2 档 OTM 候选合约（全 strike 宇宙，调用方再按月/DTE 过滤）。

    返回每个候选带 otm_rank（1=最浅虚）。同一档可能跨多个合约月。
    注：浅虚档基于全 strike 宇宙；实际选月在 pick_contract_for_event 内按月内 strike 重排，
    避免选到只在远月才上市的 OTM strike。
    """
    contracts = list_option_contracts(sym, cp, daily_dir)
    rank_of = _rank_otm_strikes([c["strike"] for c in contracts], cp, underlying_px)
    return [dict(c, otm_rank=rank_of[c["strike"]])
            for c in contracts if c["strike"] in rank_of]


# ---------------------------------------------------------------------------
# 单合约读取 / 持有期模拟
# ---------------------------------------------------------------------------
def _load_contract(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df = df.copy()
    df["date"] = pd.to_datetime(df["datetime"]).dt.normalize()
    df = df.sort_values("date").reset_index(drop=True)
    return df


def _contract_entry_idx(df: pd.DataFrame, bd: pd.Timestamp, min_cover: pd.Timestamp) -> int | None:
    """合约若在 break_date 后紧贴(<=MAX_ENTRY_GAP)上市且覆盖足够，返回入场行号，否则 None。"""
    if df.empty:
        return None
    after = df.index[df["date"] > bd]
    if len(after) == 0:
        return None
    entry_idx = int(after[0])
    if (df["date"].iloc[entry_idx] - bd).days > MAX_ENTRY_GAP_DAYS:
        return None        # 远月合约数据从晚期才开始 → 破位时未上市，排除
    if df["date"].iloc[-1] < min_cover:
        return None        # 覆盖不足 30 自然日（近似 DTE 太短）
    return entry_idx


def pick_contract_for_event(sym: str, cp: str, break_date: str, underlying_px: float,
                            daily_dir: Path = DAILY_DIR) -> dict | None:
    """为单事件选合约：取数据覆盖 >= MIN_DTE_DAYS 且破位时已上市的**最近**月，
    在该月内 strike 网格里选最浅虚 OTM（rank1 优先，缺则 rank2）。

    按月内 strike 重排 OTM（而非全 strike 宇宙），避免选到只在远月才上市的 OTM strike。
    返回 {contract..., df, entry_idx} 或 None（无可用合约 = skipped_no_option）。
    """
    bd = pd.Timestamp(break_date).normalize()
    min_cover = bd + pd.Timedelta(days=MIN_DTE_DAYS)
    contracts = list_option_contracts(sym, cp, daily_dir)

    # 按月分组，月份近者优先
    months = sorted({c["month"] for c in contracts}, key=_yymm_to_expiry_floor)
    for month in months:
        if _yymm_to_expiry_floor(month) < bd:
            continue  # 交割月早于破位日，跳过（不可能是有效持仓月）
        in_month = [c for c in contracts if c["month"] == month]
        rank_of = _rank_otm_strikes([c["strike"] for c in in_month], cp, underlying_px)
        # 月内按 otm_rank 升序（rank1 最浅虚优先）
        ranked = sorted(
            (dict(c, otm_rank=rank_of[c["strike"]]) for c in in_month if c["strike"] in rank_of),
            key=lambda c: c["otm_rank"],
        )
        for c in ranked:
            df = _load_contract(c["path"])
            entry_idx = _contract_entry_idx(df, bd, min_cover)
            if entry_idx is not None:
                return dict(c, df=df, entry_idx=entry_idx)
    return None


def simulate_event(sym: str, side: str, break_date: str, underlying_px: float,
                   daily_dir: Path = DAILY_DIR) -> dict:
    """模拟单事件。返回明细 dict；evaluated=False 表示 skipped_no_option。"""
    cp = "P" if side == "put" else "C"
    tick = TICK_SIZE[sym]
    picked = pick_contract_for_event(sym, cp, break_date, underlying_px, daily_dir)
    if picked is None:
        return {
            "symbol": sym, "side": side, "break_date": break_date,
            "break_close": underlying_px, "evaluated": False,
            "exit_reason": "skipped_no_option", "contract": None,
            "strike": None, "entry": None, "exit": None, "multiple": None,
        }

    df = picked["df"]
    i0 = picked["entry_idx"]
    entry_open = float(df["open"].iloc[i0])
    entry_fill = entry_open + SLIP_TICKS * tick          # 买入更贵
    stop_price = entry_fill * STOP_FRAC

    hold = df.iloc[i0:i0 + HOLD_DAYS].reset_index(drop=True)
    exit_reason = None
    exit_raw = None
    for j in range(len(hold)):
        low = float(hold["low"].iloc[j])
        if low <= stop_price:
            exit_raw = stop_price                         # 当日以止损价成交（保守）
            exit_reason = "stop"
            break
    if exit_reason is None:
        if len(hold) >= HOLD_DAYS:
            exit_raw = float(hold["close"].iloc[HOLD_DAYS - 1])
            exit_reason = "time"
        else:
            exit_raw = float(hold["close"].iloc[-1])      # 数据断档：最后可用收盘
            exit_reason = "data_gap"

    exit_fill = max(exit_raw - SLIP_TICKS * tick, 0.0)    # 卖出更便宜，不为负
    multiple = exit_fill / entry_fill if entry_fill > 0 else 0.0
    contract_name = picked["path"].stem  # e.g. SHFE.ag2408C7000

    return {
        "symbol": sym, "side": side, "break_date": break_date,
        "break_close": underlying_px, "evaluated": True,
        "contract": contract_name, "month": picked["month"],
        "strike": picked["strike"], "otm_rank": picked["otm_rank"],
        "entry_date": str(df["date"].iloc[i0].date()),
        "entry": round(entry_fill, 4), "stop_price": round(stop_price, 4),
        "exit": round(exit_fill, 4), "exit_reason": exit_reason,
        "multiple": round(multiple, 6),
    }


# ---------------------------------------------------------------------------
# 事件获取
# ---------------------------------------------------------------------------
def fetch_events(symbols: list[str], since: str) -> list[dict]:
    """subprocess 跑 scan_tbreak_chain，取 SHFE ag/au/cu/rb 事件。"""
    with tempfile.NamedTemporaryFile("r", suffix=".json", delete=False) as tf:
        tmp = Path(tf.name)
    try:
        subprocess.run(
            [sys.executable, str(SCAN_SCRIPT), "--pool", "CN_COMMODITY",
             "--since", since, "-o", str(tmp)],
            cwd=str(SRC_DIR), check=True, capture_output=True, text=True,
        )
        data = json.loads(tmp.read_text())
    finally:
        tmp.unlink(missing_ok=True)
    cn = data.get("CN_COMMODITY", {})
    events: list[dict] = []
    for sym in symbols:
        key = POOL_KEY.get(sym)
        if key is None:
            continue
        for ev in cn.get(key, []):
            side = "put" if ev["candidate"] == "put_candidate" else "call"
            events.append({
                "symbol": sym, "side": side,
                "break_date": ev["break_date"],
                "break_close": ev["break_close"],
            })
    events.sort(key=lambda e: (e["symbol"], e["break_date"]))
    return events


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------
def bootstrap_ci(multiples: list[float], n: int = BOOTSTRAP_N,
                 seed: int = BOOTSTRAP_SEED) -> list[float]:
    if not multiples:
        return [float("nan"), float("nan")]
    rng = np.random.default_rng(seed)
    arr = np.asarray(multiples, dtype=float)
    means = rng.choice(arr, size=(n, arr.size), replace=True).mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return [round(float(lo), 6), round(float(hi), 6)]


def _group_stats(rows: list[dict]) -> dict:
    mults = [r["multiple"] for r in rows if r.get("evaluated")]
    if not mults:
        return {"n": 0, "ev": None, "ci95": [float("nan"), float("nan")]}
    return {
        "n": len(mults),
        "ev": round(float(np.mean(mults)), 6),
        "ci95": bootstrap_ci(mults),
    }


def build_report(events: list[dict], daily_dir: Path = DAILY_DIR) -> dict:
    details = [simulate_event(e["symbol"], e["side"], e["break_date"],
                              e["break_close"], daily_dir) for e in events]
    evaluated = [d for d in details if d["evaluated"]]
    skipped = [d for d in details if not d["evaluated"]]
    mults = [d["multiple"] for d in evaluated]

    by_side = {s: _group_stats([d for d in evaluated if d["side"] == s])
               for s in ("put", "call")}
    syms = sorted({d["symbol"] for d in details})
    by_symbol = {s: _group_stats([d for d in evaluated if d["symbol"] == s])
                 for s in syms}

    return {
        "params": {
            "stop_frac": STOP_FRAC, "hold_days": HOLD_DAYS,
            "slip_ticks": SLIP_TICKS, "min_dte_days": MIN_DTE_DAYS,
            "max_entry_gap_days": MAX_ENTRY_GAP_DAYS,
            "otm_max_rank": OTM_MAX_RANK, "tick_size": TICK_SIZE,
            "bootstrap_n": BOOTSTRAP_N, "bootstrap_seed": BOOTSTRAP_SEED,
            "entry": "next-trading-day open + slip", "exit": "stop@low | time@close | data_gap",
            "multiple": "exit_fill / entry_fill",
        },
        "n_events_total": len(details),
        "n_evaluated": len(evaluated),
        "n_skipped_no_option": len(skipped),
        "premium_multiple_ev": round(float(np.mean(mults)), 6) if mults else None,
        "ci95": bootstrap_ci(mults),
        "by_side": by_side,
        "by_symbol": by_symbol,
        "events": details,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbols", default="ag,au,cu,rb",
                    help="逗号分隔短代码（ag,au,cu,rb）")
    ap.add_argument("--since", default="2024-07-01")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    events = fetch_events(symbols, args.since)
    report = build_report(events)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    # 只打印统计落盘提示，不解读、不打 PASS/FAIL
    print(f"wrote {args.out}  "
          f"(n_total={report['n_events_total']} "
          f"n_eval={report['n_evaluated']} "
          f"n_skip={report['n_skipped_no_option']})")


if __name__ == "__main__":
    main()
