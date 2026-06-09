"""Producer-side contract for backtest --out-json output (backtest_output_v1).

Shared by backtest_full_stack.py and the K=3 backtests so the validator
(validate_baselines.py --full) can parse a stable structure and diff it
against baselines/*.json. See docs/superpowers/specs/2026-06-09-baseline-validation-schema-design.md.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

SCHEMA = "backtest_output_v1"

_OHLCV = ("timestamp", "open", "high", "low", "close", "volume")


def compute_data_hash(bars: list[tuple[str, pd.DataFrame]]) -> str:
    """sha256 over a content digest of each symbol's OHLCV rows.

    Faithful to what fed the EV: catches middle-row edits, OHLC revisions,
    truncation/insertion (first+last rows included via full serialization).
    """
    h = hashlib.sha256()
    for symbol, df in sorted(bars, key=lambda t: t[0]):
        h.update(symbol.encode())
        sub = df.sort_values("timestamp") if "timestamp" in df.columns else df
        cols = [c for c in _OHLCV if c in sub.columns]
        h.update(sub[cols].to_csv(index=False).encode())
    return "sha256:" + h.hexdigest()


_PERIOD_TO_FOLD = {"IS": "is", "OOS1": "f1", "OOS2": "f2", "OOS3": "f3"}


def fold_samples_from_period_df(df, r_col: str = "r", period_col: str = "period") -> dict:
    """Build the {is,f1,f2,f3} samples dict from a trades DataFrame whose rows
    carry a period label (IS/OOS1/OOS2/OOS3) and a realized-R column."""
    out: dict[str, dict] = {}
    for raw_label, key in _PERIOD_TO_FOLD.items():
        sub = df[df[period_col] == raw_label]
        if len(sub):
            out[key] = {
                "n": int(len(sub)),
                "ev_r": round(float(sub[r_col].mean()), 3),
                "win_pct": round(float((sub[r_col] > 0).mean() * 100), 1),
            }
        else:
            out[key] = {"n": None, "ev_r": None, "win_pct": None}
    return out


_KINDS = ("folds", "full_stack")


def write_baseline_output(path, *, kind: str, **payload) -> None:
    """Serialize a backtest_output_v1 doc. payload is the kind-specific body
    (folds: lane/pool/samples/data_hash/params_echo; full_stack: lanes/data_hash)."""
    if kind not in _KINDS:
        raise ValueError(f"unknown kind {kind!r}; expected one of {_KINDS}")
    doc = {"schema": SCHEMA, "kind": kind, **payload}
    Path(path).write_text(json.dumps(doc, indent=2, default=str), encoding="utf-8")
