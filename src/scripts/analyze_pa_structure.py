"""PA Structure Analysis — Three-Layer Framework for CN_COMMODITY.

Layer 1: Daily PA structure per symbol (BULL / TR / TR_FORMING / BEAR / UNCLEAR)
Layer 2: Multi-TF MACD context (daily / 60min / 15min DIF alignment)
Layer 3: Implied entry framework per phase

Usage:
    python scripts/analyze_pa_structure.py --pool CN_COMMODITY
    python scripts/analyze_pa_structure.py --pool CN_COMMODITY --bars-dir data/bars
    python scripts/analyze_pa_structure.py --pool CN_COMMODITY --quant-data-root /path/to/quant
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from data import bar_loader
from engine.divergence.pa_structure import PAStructureDetector
from engine.features.macd import macd as compute_macd

# ---------------------------------------------------------------------------
# Pool definitions (mirrors score_today.py)
# ---------------------------------------------------------------------------

CN_COMMODITY_PURE = [
    "kq_m_shfe_rb",
    "kq_m_dce_m", "kq_m_dce_i", "kq_m_dce_j", "kq_m_dce_jm",
    "kq_m_dce_p", "kq_m_dce_y",
    "kq_m_czce_ta", "kq_m_czce_ma", "kq_m_czce_cf", "kq_m_czce_sr",
    "kq_m_ine_sc",
]

CN_COMMODITY_ALL = [
    "kq_m_shfe_rb", "kq_m_shfe_cu", "kq_m_shfe_au", "kq_m_shfe_ag",
    "kq_m_dce_m", "kq_m_dce_i", "kq_m_dce_j", "kq_m_dce_jm",
    "kq_m_dce_p", "kq_m_dce_y",
    "kq_m_czce_ta", "kq_m_czce_ma", "kq_m_czce_cf", "kq_m_czce_sr",
    "kq_m_ine_sc",
]

POOLS: dict[str, list[str]] = {
    "CN_COMMODITY": CN_COMMODITY_PURE,
    "CN_COMMODITY_ALL": CN_COMMODITY_ALL,
}

SHORT_NAMES: dict[str, str] = {
    "kq_m_shfe_rb":  "rb(螺纹)",
    "kq_m_shfe_cu":  "cu(铜)",
    "kq_m_shfe_au":  "au(金)",
    "kq_m_shfe_ag":  "ag(银)",
    "kq_m_dce_m":    "m(豆粕)",
    "kq_m_dce_i":    "i(铁矿)",
    "kq_m_dce_j":    "j(焦炭)",
    "kq_m_dce_jm":   "jm(焦煤)",
    "kq_m_dce_p":    "p(棕榈)",
    "kq_m_dce_y":    "y(豆油)",
    "kq_m_czce_ta":  "ta(PTA)",
    "kq_m_czce_ma":  "ma(甲醇)",
    "kq_m_czce_cf":  "cf(棉花)",
    "kq_m_czce_sr":  "sr(白糖)",
    "kq_m_ine_sc":   "sc(原油)",
}

PHASE_EMOJI: dict[str, str] = {
    "BULL":       "↑BULL",
    "TR":         "◈TR",
    "TR_FORMING": "~TR_F",
    "BEAR":       "↓BEAR",
    "UNCLEAR":    "?UNCL",
}


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def _load(sym: str, freq: str, args) -> pd.DataFrame | None:
    """Load bars for sym at given frequency. freq: 'daily', '60', '15'."""
    if getattr(args, "quant_data_root", None) is not None:
        resolved = bar_loader.infer_symbol_and_mic(sym)
        if resolved is not None:
            quant_sym, mic = resolved
            level = {"daily": "D", "60": "60min", "15": "15min"}[freq]
            try:
                df = bar_loader.load_bars_quant(quant_sym, mic, level, args.quant_data_root)
                if not df.empty:
                    return df
            except Exception:
                pass

    suffix = {"daily": "daily", "60": "60", "15": "15"}[freq]
    path = args.bars_dir / f"{sym.lower()}_{suffix}.json"
    if not path.exists():
        return None
    try:
        return bar_loader.load_bars_json(path)
    except Exception:
        return None


def _dif_sign(bars: pd.DataFrame | None) -> str:
    """Returns '+' (DIF>0 bullish), '-' (DIF<0 bearish), or '?' if unavailable."""
    if bars is None or len(bars) < 30:
        return "?"
    try:
        md = compute_macd(bars["close"])
        dif = float(md["dif"].iloc[-1])
        return "+" if dif > 0 else "-"
    except Exception:
        return "?"


def _dif_val(bars: pd.DataFrame | None) -> float | None:
    if bars is None or len(bars) < 30:
        return None
    try:
        md = compute_macd(bars["close"])
        return float(md["dif"].iloc[-1])
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------

def analyze_symbol(sym: str, args) -> dict | None:
    daily = _load(sym, "daily", args)
    if daily is None or len(daily) < 60:
        return None

    h60 = _load(sym, "60", args)
    h15 = _load(sym, "15", args)

    # Layer 1 — daily PA structure
    det = PAStructureDetector()
    struct = det.detect(daily, up_to_idx=len(daily) - 1)
    close = float(daily["close"].iloc[-1])
    date = str(pd.Timestamp(daily["timestamp"].iloc[-1]).date())

    # Layer 2 — multi-TF MACD
    d_dif = _dif_val(daily)
    d_sign = "+" if (d_dif or 0) > 0 else "-"
    h60_sign = _dif_sign(h60)
    h15_sign = _dif_sign(h15)

    # Alignment assessment
    # h=opposing means h60 DIF opposes daily direction (if daily -, h60 - = aligned, h60 + = not opp)
    # For long setups: daily DIF < 0 (daily downtrend but looking for bottom)
    #   h60 DIF < 0 = h=opposing (60min bearish while we look for daily bounce)
    #   h15 DIF flipping + = early momentum confirmation
    alignment = _assess_alignment(d_sign, h60_sign, h15_sign, struct.phase)

    return {
        "sym": sym,
        "close": close,
        "date": date,
        "phase": struct.phase,
        "tr_top": struct.tr_top,
        "tr_bot": struct.tr_bot,
        "pos_in_tr": struct.pos_in_tr,
        "at_tr_bottom": struct.at_tr_bottom,
        "tr_range_pct": struct.tr_range_pct,
        "structural_stop": struct.structural_stop,
        "d_dif": d_sign,
        "h60_dif": h60_sign,
        "h15_dif": h15_sign,
        "alignment": alignment,
    }


def _assess_alignment(d: str, h60: str, h15: str, phase: str) -> str:
    """Classify the multi-TF MACD relationship for a LONG setup."""
    if phase == "BEAR":
        return "skip_bear"
    if phase == "BULL":
        if d == "+":
            return "bull_aligned" if h60 == "+" else "bull_h60_opp"
        return "bull_d_neg"
    # TR / TR_FORMING
    if d == "+" and h60 == "+" and h15 == "+":
        return "all_bull_late"
    if d == "-" and h60 == "-" and h15 == "-":
        return "all_bear_wait"          # fully bearish — wait for h15 flip
    if d == "-" and h60 == "-" and h15 == "+":
        return "h15_flip_watch"         # 15min turning — watch for confirmation
    if d == "-" and h60 == "+" and h15 == "+":
        return "h60_not_opp"            # 60min already bullish — not classic h=opp
    if d == "+" and h60 == "-" and h15 == "-":
        return "d_bull_h60_opp_wait"    # daily bullish, 60min still bearish
    if d == "+" and h60 == "-" and h15 == "+":
        return "d_bull_h60_opp_h15_up"  # 60min opposing, 15min flipping
    return f"d={d}/60={h60}/15={h15}"


def _phase_action(phase: str, at_bot: bool, alignment: str) -> str:
    """One-line action implication per the three-layer framework."""
    if phase == "BEAR":
        return "不做多，等结构反转"
    if phase == "BULL":
        if "aligned" in alignment:
            return "顺势，回调接（结构性止损在最近HH）"
        return "BULL但60min对立，等60min确认"
    if phase in ("TR", "TR_FORMING"):
        if at_bot:
            if alignment in ("all_bear_wait", "h15_flip_watch"):
                return "TR底部 + 60min对立 → 观察15min翻多信号"
            if "h15_flip" in alignment:
                return "TR底部 + 15min正在翻多 → 入场候选"
            return "TR底部，但多空不明，等待"
        return "TR但未到底部区间，等价格下探"
    return "结构不明，暂不操作"


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_report(results: list[dict]) -> None:
    if not results:
        print("无数据。")
        return

    # Sort: BEAR last, then by phase, then by pos_in_tr (bottom first)
    phase_order = {"TR": 0, "TR_FORMING": 1, "BULL": 2, "UNCLEAR": 3, "BEAR": 4}
    results.sort(key=lambda r: (
        phase_order.get(r["phase"], 9),
        (r["pos_in_tr"] or 1.0),
    ))

    print()
    print("=" * 90)
    print("CN_COMMODITY — Layer 1: Daily PA Structure")
    print("=" * 90)
    hdr = f"{'品种':<14} {'相位':<8} {'区间%':<7} {'位置':<7} {'底部':<5} {'结构止损':<12} {'close':<10} {'日期'}"
    print(hdr)
    print("-" * 90)
    for r in results:
        name = SHORT_NAMES.get(r["sym"], r["sym"])
        phase_str = PHASE_EMOJI.get(r["phase"], r["phase"])
        rng = f"{r['tr_range_pct']:.1f}%" if r["tr_range_pct"] is not None else "—"
        pos = f"{r['pos_in_tr']:.0%}" if r["pos_in_tr"] is not None else "—"
        at_bot = "✓" if r["at_tr_bottom"] else "—"
        stop = f"{r['structural_stop']:.1f}" if r["structural_stop"] is not None else "—"
        print(f"{name:<14} {phase_str:<8} {rng:<7} {pos:<7} {at_bot:<5} {stop:<12} {r['close']:<10.1f} {r['date']}")

    print()
    print("=" * 90)
    print("CN_COMMODITY — Layer 2: 多周期 MACD 力量对比")
    print("  + = DIF>0 (多方)   - = DIF<0 (空方)   ? = 数据不足")
    print("=" * 90)
    hdr2 = f"{'品种':<14} {'相位':<8} {'日线':<5} {'60min':<7} {'15min':<7} {'对比评估'}"
    print(hdr2)
    print("-" * 90)
    for r in results:
        name = SHORT_NAMES.get(r["sym"], r["sym"])
        phase_str = PHASE_EMOJI.get(r["phase"], r["phase"])
        print(f"{name:<14} {phase_str:<8} {r['d_dif']:<5} {r['h60_dif']:<7} {r['h15_dif']:<7} {r['alignment']}")

    print()
    print("=" * 90)
    print("CN_COMMODITY — Layer 3: 基于结构的入场框架")
    print("=" * 90)
    hdr3 = f"{'品种':<14} {'相位':<8} {'操作建议'}"
    print(hdr3)
    print("-" * 90)
    for r in results:
        name = SHORT_NAMES.get(r["sym"], r["sym"])
        phase_str = PHASE_EMOJI.get(r["phase"], r["phase"])
        action = _phase_action(r["phase"], r["at_tr_bottom"], r["alignment"])
        print(f"{name:<14} {phase_str:<8} {action}")

    print()
    print("─" * 90)
    print("止损框架参考:")
    print("  TR 阶段  → 结构性止损 = TR 底部 × (1 - 1%)，风险敞口 ≤ 2R")
    print("  BULL 阶段 → 最近确认 HH（Higher Low）× (1 - 1%)")
    print("  入场时机  → 日线信号 + 60min h=opp(DIF<0) + 15min DIF翻正 = 三重确认")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="PA structure analysis")
    parser.add_argument("--pool", default="CN_COMMODITY",
                        choices=list(POOLS.keys()),
                        help="Symbol pool to analyze")
    parser.add_argument("--bars-dir", type=Path,
                        default=Path(__file__).parent.parent / "data" / "raw",
                        help="Directory with *_daily.json, *_60.json, *_15.json files")
    parser.add_argument("--quant-data-root", type=Path, default=None,
                        help="Quant-data Parquet store root (preferred over JSON)")
    args = parser.parse_args()

    symbols = POOLS[args.pool]
    results = []
    for sym in symbols:
        r = analyze_symbol(sym, args)
        if r is None:
            print(f"  [skip] {sym} — 数据不足", file=sys.stderr)
        else:
            results.append(r)

    print_report(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
