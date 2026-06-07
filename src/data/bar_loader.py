"""bar_loader.py — shared OHLCV loading helpers for analysis scripts.

Two data sources:
  JSON  : legacy snapshot files written by fetch_polygon / fetch_akshare / fetch_tqsdk
  Quant : quant-data Parquet store read via data.store.BarStore

The returned DataFrame always contains:
  timestamp  pd.Timestamp  UTC tz-aware
  open, high, low, close   float
  volume                   float (may be NaN)
  time                     int   Unix seconds (TV export / engine compatibility)
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

DEFAULT_QUANT_ROOT: Path = Path(__file__).resolve().parent / "quant"


# ---------------------------------------------------------------------------
# Level / suffix mapping tables
# ---------------------------------------------------------------------------

# JSON filename suffix → BarStore level string
FILENAME_SUFFIX_TO_BARSTORE_LEVEL: dict[str, str] = {
    "daily":  "D",
    "weekly": "W",
    "60":     "60min",
    "4h":     "4h",
    "30":     "30min",
    "15":     "15min",
    "5":      "5min",
    "1":      "1min",
}

# Engine level_id (detect_all_divergences) → BarStore level string
ENGINE_LEVEL_TO_BARSTORE: dict[str, str] = {
    "D":   "D",
    "W":   "W",
    "1h":  "60min",
    "60m": "60min",
    "4h":  "4h",
    "30m": "30min",
    "15m": "15min",
    "5m":  "5min",
    "1m":  "1min",
}

# BarStore level string → engine level_id
BARSTORE_TO_ENGINE_LEVEL: dict[str, str] = {
    "D":     "D",
    "W":     "W",
    "60min": "1h",
    "4h":    "4h",
    "30min": "30m",
    "15min": "15m",
    "5min":  "5m",
    "1min":  "1m",
}

# Exchange suffix → MIC code (dot-notation symbols like "RB2501.SHFE")
_SUFFIX_TO_MIC: dict[str, str] = {
    "SH":     "XSHG",
    "SSE":    "XSHG",
    "SZ":     "XSHE",
    "SZSE":   "XSHE",
    "SHFE":   "XSHF",
    "DCE":    "XDCE",
    "CZCE":   "XZCE",
    "CFFEX":  "XCFE",
    "INE":    "XINE",
    "GFEX":   "XGFE",
    "NYSE":   "XNYS",
    "NASDAQ": "XNAQ",
    "NQ":     "XNAQ",
}

# kq_m_ exchange key → MIC
_KQ_M_EXCHANGE_TO_MIC: dict[str, str] = {
    "cffex": "XCFE",
    "shfe":  "XSHF",
    "dce":   "XDCE",
    "czce":  "XZCE",
    "ine":   "XINE",
    "gfex":  "XGFE",
}

# kq_m_ exchanges whose AkShare symbol uses uppercase tickers (IF0, MA0)
_KQ_M_UPPERCASE_EXCHANGES: frozenset[str] = frozenset({"cffex", "czce"})


# ---------------------------------------------------------------------------
# KQData continuous contract symbol translation
# ---------------------------------------------------------------------------

def _kq_m_to_quant(kq_symbol: str) -> tuple[str, str] | None:
    """Convert a kq_m_ KQData continuous contract symbol to (quant_symbol, mic).

    Examples::
      "kq_m_cffex_if"  → ("IF0", "XCFE")
      "kq_m_shfe_rb"   → ("rb0", "XSHF")
      "kq_m_czce_ma"   → ("MA0", "XZCE")
      "kq_m_ine_sc"    → ("sc0", "XINE")

    Returns None if the symbol doesn't follow the kq_m_ pattern or the
    exchange is unrecognized.
    """
    lower = kq_symbol.lower()
    if not lower.startswith("kq_m_"):
        return None
    rest = lower[len("kq_m_"):]
    parts = rest.split("_", 1)
    if len(parts) != 2:
        return None
    exchange_key, instrument = parts
    mic = _KQ_M_EXCHANGE_TO_MIC.get(exchange_key)
    if mic is None:
        return None
    sym = instrument.upper() + "0" if exchange_key in _KQ_M_UPPERCASE_EXCHANGES else instrument.lower() + "0"
    return sym, mic


# ---------------------------------------------------------------------------
# Exchange inference
# ---------------------------------------------------------------------------

def infer_exchange_mic(symbol: str) -> str | None:
    """Return MIC exchange code for a symbol, or None if not yet supported."""
    sym_lower = symbol.lower()
    if sym_lower.startswith("kq_m_"):
        result = _kq_m_to_quant(sym_lower)
        return result[1] if result else None
    if "." in symbol:
        suffix = symbol.rsplit(".", 1)[-1].upper()
        return _SUFFIX_TO_MIC.get(suffix)  # None if unrecognized
    return "XNYS"  # plain ticker defaults to NYSE


def infer_symbol_and_mic(symbol: str) -> tuple[str, str] | None:
    """Return (quant_symbol, mic) for loading from BarStore, or None.

    For kq_m_ continuous contracts, translates to the quant-data symbol
    (e.g. "kq_m_shfe_rb" → ("rb0", "XSHF")).  For all other symbols,
    returns (symbol.upper(), mic).

    Use this instead of combining sym.upper() + infer_exchange_mic() so
    that kq_m_ symbols resolve to the correct BarStore key.
    """
    sym_lower = symbol.lower()
    if sym_lower.startswith("kq_m_"):
        return _kq_m_to_quant(sym_lower)
    mic = infer_exchange_mic(symbol)
    if mic is None:
        return None
    return symbol.upper(), mic


def parse_snapshot_name(snapshot_name: str) -> tuple[str, str, str] | None:
    """Infer (quant_symbol, exchange_mic, barstore_level) from a snapshot filename.

    Examples::
      "spy_daily.json"          → ("SPY",  "XNYS", "D")
      "spy_60.json"             → ("SPY",  "XNYS", "60min")
      "kq_m_cffex_if_daily.json"→ ("IF0",  "XCFE", "D")
      "kq_m_shfe_rb_daily.json" → ("rb0",  "XSHF", "D")

    Returns None for unrecognized exchange suffixes or unknown level suffixes.
    """
    stem = Path(snapshot_name).stem  # strip .json
    idx = stem.rfind("_")
    if idx == -1:
        return None
    sym_raw = stem[:idx]
    suffix = stem[idx + 1:]
    level = FILENAME_SUFFIX_TO_BARSTORE_LEVEL.get(suffix)
    if level is None:
        return None

    # kq_m_ continuous contracts need symbol translation
    if sym_raw.lower().startswith("kq_m_"):
        result = _kq_m_to_quant(sym_raw)
        if result is None:
            return None
        quant_sym, mic = result
        return quant_sym, mic, level

    mic = infer_exchange_mic(sym_raw)
    if mic is None:
        return None
    return sym_raw.upper(), mic, level


# ---------------------------------------------------------------------------
# JSON loaders (legacy)
# ---------------------------------------------------------------------------

def load_bars_json(path: Path) -> pd.DataFrame:
    """Load bars from a legacy JSON snapshot.  Adds 'time' column if missing."""
    payload = json.loads(path.read_text())
    bars_raw = payload.get("bars", payload) if isinstance(payload, dict) else payload
    df = pd.DataFrame(bars_raw)
    if "timestamp" not in df.columns:
        df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
    if "time" not in df.columns:
        df["time"] = df["timestamp"].values.astype("datetime64[s]").astype("int64")
    return df.sort_values("timestamp").reset_index(drop=True)


def load_snapshot_json(path: Path) -> tuple[pd.DataFrame, dict]:
    """Like load_bars_json but also returns the raw payload dict."""
    payload = json.loads(path.read_text())
    bars_raw = payload.get("bars", payload) if isinstance(payload, dict) else payload
    df = pd.DataFrame(bars_raw)
    if "timestamp" not in df.columns:
        df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
    if "time" not in df.columns:
        df["time"] = df["timestamp"].values.astype("datetime64[s]").astype("int64")
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df, payload


# ---------------------------------------------------------------------------
# BarStore loaders (quant-data)
# ---------------------------------------------------------------------------

def load_bars_quant(
    symbol: str,
    exchange_mic: str,
    barstore_level: str,
    data_root: Path,
    *,
    start=None,
    end=None,
) -> pd.DataFrame:
    """Load bars from quant-data Parquet store.  Adds 'time' column (Unix seconds)."""
    from data.store import BarStore  # lazy import to avoid heavy dep at module level
    store = BarStore(data_root)
    bf = store.load_barframe(symbol, exchange_mic, barstore_level, start=start, end=end)
    df = bf.df.copy()
    df["time"] = df["timestamp"].values.astype("datetime64[s]").astype("int64")
    return df


def load_bars_quant_or_json(
    symbol: str,
    suffix: str,
    fallback_dir: Path,
    *,
    quant_root: Path | None = None,
) -> pd.DataFrame | None:
    """Try Parquet first, fall back to legacy JSON snapshot.

    Used by backtest scripts that historically read ``<sym><suffix>.json``
    from ``data/raw/``.  The Parquet store has full intraday history for
    symbols whose JSON snapshots were truncated during migration
    (shfe ag/au/cu, ine sc).  Returns ``None`` if neither source matches.

    ``suffix`` is the legacy JSON filename suffix (``_daily`` / ``_60`` /
    ``_15`` / ``_30`` / ``_5`` / ``_1``).
    """
    level = FILENAME_SUFFIX_TO_BARSTORE_LEVEL.get(suffix.lstrip("_"))
    resolved = infer_symbol_and_mic(symbol)
    if level is not None and resolved is not None:
        quant_sym, mic = resolved
        root = quant_root if quant_root is not None else DEFAULT_QUANT_ROOT
        try:
            return load_bars_quant(quant_sym, mic, level, root)
        except Exception:
            pass
    candidates = list(fallback_dir.glob(f"**/{symbol}{suffix}.json"))
    if not candidates:
        return None
    return load_bars_json(candidates[0])


def load_snapshot_quant(
    symbol: str,
    exchange_mic: str,
    barstore_level: str,
    data_root: Path,
    *,
    start=None,
    end=None,
) -> tuple[pd.DataFrame, dict]:
    """Load bars from BarStore and return (df, meta_dict) matching JSON payload shape."""
    df = load_bars_quant(symbol, exchange_mic, barstore_level, data_root, start=start, end=end)
    engine_level = BARSTORE_TO_ENGINE_LEVEL.get(barstore_level, barstore_level)
    meta: dict = {
        "symbol": symbol,
        "resolution": engine_level,
        "source": "quant_data",
    }
    return df, meta
