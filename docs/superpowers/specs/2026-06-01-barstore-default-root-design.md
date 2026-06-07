# BarStore Default Root

**Date:** 2026-06-01
**Status:** Approved

---

## Goal

Make `data/quant/` (the quant-data Parquet store) the automatic default for all 16 analysis scripts, so `python analyze.py SPY` tries BarStore first and falls back to JSON — no `--quant-data-root` flag required.

---

## Scope

**In scope:**
- `src/data/bar_loader.py` — add `DEFAULT_QUANT_ROOT` constant
- 16 scripts in `src/scripts/` — change argparse `default=None` → `default=bar_loader.DEFAULT_QUANT_ROOT`
- `backtest_signals.py` and `backtest_cn_futures.py` — same change via their manual argv parsing

**Out of scope:**
- Wiring `quant_root` into `backtest_cn_b_topology.py` and `backtest_cn_futures.py` loading functions (they remain no-op; flag is accepted but loading reads JSON directly)
- New loading logic — the existing try/except BarStore-first / JSON-fallback is already correct
- New tests — this is a pure default-value change

---

## Design

### `src/data/bar_loader.py`

Add one constant near the top of the file (after imports):

```python
DEFAULT_QUANT_ROOT: Path = Path(__file__).resolve().parent / "quant"
```

Resolves to `src/data/quant/` — same path all 8 per-script constants currently use.

### Script changes: 3 groups

**Group 1 — 8 scripts with a local `DEFAULT_QUANT_ROOT`**

Files: `analyze.py`, `analyze_sweet_spots.py`, `demo_features.py`, `demo_divergence.py`, `demo_fusion.py`, `scan_portfolio_b.py`, `score_today.py`, `export_signals_for_tv.py`

For each:
1. Remove local `DEFAULT_QUANT_ROOT = Path(__file__).resolve().parents[1] / "data" / "quant"` line
2. Change argparse argument from `default=None` to `default=bar_loader.DEFAULT_QUANT_ROOT`

**Group 2 — 6 scripts with argparse but no local constant**

Files: `backtest_fusion.py`, `backtest_fusion_d1h15m.py`, `backtest_b_topology_multi.py`, `backtest_rr_pool.py`, `backtest_rr_intraday.py`, `backtest_cn_b_topology.py`

For each:
- Change argparse `--quant-data-root` from `default=None` to `default=bar_loader.DEFAULT_QUANT_ROOT`

**Group 3 — 2 scripts with manual argv parsing**

- `backtest_signals.py`: change `quant_root: Path | None = None` → `quant_root: Path = bar_loader.DEFAULT_QUANT_ROOT`
- `backtest_cn_futures.py`: same — behavior stays identical since loading functions don't consult `quant_root`

### Behaviour

```
# Before — BarStore only used when flag is passed explicitly:
python analyze.py SPY --quant-data-root /path/to/data/quant

# After — BarStore tried automatically, JSON fallback if Parquet absent:
python analyze.py SPY
# stderr: "quant load SPY/daily: ... — falling back to JSON"  (only if data/quant/ empty)
```

The `--quant-data-root` flag remains usable to override with a different path.

---

## Files Changed

| File | Change |
|---|---|
| `src/data/bar_loader.py` | Add `DEFAULT_QUANT_ROOT` constant |
| `src/scripts/analyze.py` | Remove local const; change argparse default |
| `src/scripts/analyze_sweet_spots.py` | Remove local const; change argparse default |
| `src/scripts/demo_features.py` | Remove local const; change argparse default |
| `src/scripts/demo_divergence.py` | Remove local const; change argparse default |
| `src/scripts/demo_fusion.py` | Remove local const; change argparse default |
| `src/scripts/scan_portfolio_b.py` | Remove local const; change argparse default |
| `src/scripts/score_today.py` | Remove local const; change argparse default |
| `src/scripts/export_signals_for_tv.py` | Remove local const; change argparse default |
| `src/scripts/backtest_fusion.py` | Change argparse default |
| `src/scripts/backtest_fusion_d1h15m.py` | Change argparse default |
| `src/scripts/backtest_b_topology_multi.py` | Change argparse default |
| `src/scripts/backtest_rr_pool.py` | Change argparse default |
| `src/scripts/backtest_rr_intraday.py` | Change argparse default |
| `src/scripts/backtest_cn_b_topology.py` | Change argparse default (no-op: loading ignores flag) |
| `src/scripts/backtest_signals.py` | Change manual-parse default |
| `src/scripts/backtest_cn_futures.py` | Change manual-parse default (no-op: loading ignores flag) |
