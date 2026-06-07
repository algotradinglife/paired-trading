# BarStore Default Root Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `data/quant/` the automatic BarStore default across all 16 analysis scripts so BarStore is tried first without requiring `--quant-data-root` on every invocation.

**Architecture:** Add `DEFAULT_QUANT_ROOT` once to `bar_loader.py` (which every script already imports), then update all scripts to use it as the argparse/manual-parse default instead of `None`. No loading logic changes — the existing try/except BarStore-first / JSON-fallback is already correct in all scripts.

**Tech Stack:** Python 3.11+, `argparse`, `pathlib`, existing `data.bar_loader` / `data.store.BarStore`

---

## Files

| File | Change |
|---|---|
| `src/data/bar_loader.py` | Add `DEFAULT_QUANT_ROOT` constant |
| `src/scripts/analyze.py` | Remove local const; update argparse default + help |
| `src/scripts/analyze_sweet_spots.py` | Remove local const; update argparse default + help |
| `src/scripts/scan_portfolio_b.py` | Remove local const; update argparse default + help |
| `src/scripts/score_today.py` | Remove local const; update argparse default + help |
| `src/scripts/demo_features.py` | Remove local const; update argparse default |
| `src/scripts/demo_divergence.py` | Remove local const; update argparse default |
| `src/scripts/demo_fusion.py` | Remove local const; update argparse default |
| `src/scripts/export_signals_for_tv.py` | Remove local const; update argparse default |
| `src/scripts/backtest_fusion.py` | Update argparse default |
| `src/scripts/backtest_fusion_d1h15m.py` | Update argparse default |
| `src/scripts/backtest_b_topology_multi.py` | Update argparse default |
| `src/scripts/backtest_rr_pool.py` | Update argparse default |
| `src/scripts/backtest_rr_intraday.py` | Update argparse default |
| `src/scripts/backtest_cn_b_topology.py` | Update argparse default (no-op: loading ignores flag) |
| `src/scripts/backtest_signals.py` | Update manual-parse default |
| `src/scripts/backtest_cn_futures.py` | No change needed (flag stripped + discarded, no variable stored) |

---

### Task 1: Add `DEFAULT_QUANT_ROOT` to `bar_loader.py`

**Files:**
- Modify: `src/data/bar_loader.py`

- [ ] **Step 1: Add the constant after the `import pandas as pd` line**

In `src/data/bar_loader.py`, the top of the file reads:
```python
import json
from pathlib import Path

import pandas as pd


# ---------------------------------------------------------------------------
# Level / suffix mapping tables
```

Change to:
```python
import json
from pathlib import Path

import pandas as pd

DEFAULT_QUANT_ROOT: Path = Path(__file__).resolve().parent / "quant"


# ---------------------------------------------------------------------------
# Level / suffix mapping tables
```

- [ ] **Step 2: Run tests to confirm no regression**

```bash
cd /Users/huhan/workspace/trading/macd-momentum
python -m pytest src/tests/ -q
```

Expected: `45 passed`

- [ ] **Step 3: Commit**

```bash
cd /Users/huhan/workspace/trading/macd-momentum
git add src/data/bar_loader.py
git commit -m "feat: add DEFAULT_QUANT_ROOT constant to bar_loader"
```

---

### Task 2: Update Group 1 — 8 scripts with local `DEFAULT_QUANT_ROOT`

**Files:**
- Modify: `src/scripts/analyze.py`
- Modify: `src/scripts/analyze_sweet_spots.py`
- Modify: `src/scripts/scan_portfolio_b.py`
- Modify: `src/scripts/score_today.py`
- Modify: `src/scripts/demo_features.py`
- Modify: `src/scripts/demo_divergence.py`
- Modify: `src/scripts/demo_fusion.py`
- Modify: `src/scripts/export_signals_for_tv.py`

Each of these scripts has `DEFAULT_QUANT_ROOT = Path(__file__).resolve().parents[1] / "data" / "quant"` defined locally and uses `default=None` in its `--quant-data-root` argparse argument.

**4 scripts whose help text references `{DEFAULT_QUANT_ROOT}`**

- [ ] **Step 1: Update `src/scripts/analyze.py`**

Remove the local constant (line 36):
```python
DEFAULT_QUANT_ROOT = Path(__file__).resolve().parents[1] / "data" / "quant"
```
→ delete this line entirely.

Update the argparse argument:
```python
    p.add_argument("--quant-data-root", type=Path, default=None, dest="quant_data_root",
                   help=f"quant-data Parquet root (enables BarStore mode; default: {DEFAULT_QUANT_ROOT})")
```
→
```python
    p.add_argument("--quant-data-root", type=Path, default=bar_loader.DEFAULT_QUANT_ROOT, dest="quant_data_root",
                   help="quant-data Parquet root (default: data/quant/)")
```

- [ ] **Step 2: Update `src/scripts/analyze_sweet_spots.py`**

Remove (line 48):
```python
DEFAULT_QUANT_ROOT = Path(__file__).resolve().parents[1] / "data" / "quant"
```

Update argparse (lines 160–161):
```python
    p.add_argument("--quant-data-root", type=Path, default=None, dest="quant_data_root",
                   help=f"quant-data Parquet root (enables BarStore mode; default: {DEFAULT_QUANT_ROOT})")
```
→
```python
    p.add_argument("--quant-data-root", type=Path, default=bar_loader.DEFAULT_QUANT_ROOT, dest="quant_data_root",
                   help="quant-data Parquet root (default: data/quant/)")
```

- [ ] **Step 3: Update `src/scripts/scan_portfolio_b.py`**

Remove (line 41):
```python
DEFAULT_QUANT_ROOT = Path(__file__).resolve().parents[1] / "data" / "quant"
```

Update argparse (lines 307–308):
```python
    p.add_argument("--quant-data-root", type=Path, default=None, dest="quant_data_root",
                   help=f"quant-data Parquet root (BarStore mode for supported symbols; default: {DEFAULT_QUANT_ROOT})")
```
→
```python
    p.add_argument("--quant-data-root", type=Path, default=bar_loader.DEFAULT_QUANT_ROOT, dest="quant_data_root",
                   help="quant-data Parquet root (default: data/quant/)")
```

- [ ] **Step 4: Update `src/scripts/score_today.py`**

Remove (line 46):
```python
DEFAULT_QUANT_ROOT = Path(__file__).resolve().parents[1] / "data" / "quant"
```

Update argparse (lines 261–262):
```python
    p.add_argument("--quant-data-root", type=Path, default=None, dest="quant_data_root",
                   help=f"quant-data Parquet root (enables BarStore mode; default: {DEFAULT_QUANT_ROOT})")
```
→
```python
    p.add_argument("--quant-data-root", type=Path, default=bar_loader.DEFAULT_QUANT_ROOT, dest="quant_data_root",
                   help="quant-data Parquet root (default: data/quant/)")
```

**4 scripts whose help text does NOT reference `{DEFAULT_QUANT_ROOT}`**

For each of `demo_features.py`, `demo_divergence.py`, `demo_fusion.py`, `export_signals_for_tv.py`: remove the local constant line and change `default=None` → `default=bar_loader.DEFAULT_QUANT_ROOT` in the argparse argument.

- [ ] **Step 5: Update `src/scripts/demo_features.py`**

Remove (line 27):
```python
DEFAULT_QUANT_ROOT = Path(__file__).resolve().parents[1] / "data" / "quant"
```

Update argparse (line 149):
```python
    ap.add_argument("--quant-data-root", type=Path, default=None, dest="quant_data_root",
```
→
```python
    ap.add_argument("--quant-data-root", type=Path, default=bar_loader.DEFAULT_QUANT_ROOT, dest="quant_data_root",
```

- [ ] **Step 6: Update `src/scripts/demo_divergence.py`**

Remove (line 25):
```python
DEFAULT_QUANT_ROOT = Path(__file__).resolve().parents[1] / "data" / "quant"
```

Update argparse (line 133):
```python
    ap.add_argument("--quant-data-root", type=Path, default=None, dest="quant_data_root",
```
→
```python
    ap.add_argument("--quant-data-root", type=Path, default=bar_loader.DEFAULT_QUANT_ROOT, dest="quant_data_root",
```

- [ ] **Step 7: Update `src/scripts/demo_fusion.py`**

Remove (line 25):
```python
DEFAULT_QUANT_ROOT = Path(__file__).resolve().parents[1] / "data" / "quant"
```

Update argparse (line 143):
```python
    ap.add_argument("--quant-data-root", type=Path, default=None, dest="quant_data_root",
```
→
```python
    ap.add_argument("--quant-data-root", type=Path, default=bar_loader.DEFAULT_QUANT_ROOT, dest="quant_data_root",
```

- [ ] **Step 8: Update `src/scripts/export_signals_for_tv.py`**

Remove (line 38):
```python
DEFAULT_QUANT_ROOT = Path(__file__).resolve().parents[1] / "data" / "quant"
```

Update argparse (line 149):
```python
    ap.add_argument("--quant-data-root", type=Path, default=None, dest="quant_data_root",
```
→
```python
    ap.add_argument("--quant-data-root", type=Path, default=bar_loader.DEFAULT_QUANT_ROOT, dest="quant_data_root",
```

- [ ] **Step 9: Run tests**

```bash
cd /Users/huhan/workspace/trading/macd-momentum
python -m pytest src/tests/ -q
```

Expected: `45 passed`

- [ ] **Step 10: Commit**

```bash
cd /Users/huhan/workspace/trading/macd-momentum
git add src/scripts/analyze.py src/scripts/analyze_sweet_spots.py \
        src/scripts/scan_portfolio_b.py src/scripts/score_today.py \
        src/scripts/demo_features.py src/scripts/demo_divergence.py \
        src/scripts/demo_fusion.py src/scripts/export_signals_for_tv.py
git commit -m "feat: use bar_loader.DEFAULT_QUANT_ROOT as default in Group 1 scripts"
```

---

### Task 3: Update Group 2 (6 argparse scripts) + `backtest_signals.py`

**Files:**
- Modify: `src/scripts/backtest_fusion.py`
- Modify: `src/scripts/backtest_fusion_d1h15m.py`
- Modify: `src/scripts/backtest_b_topology_multi.py`
- Modify: `src/scripts/backtest_rr_pool.py`
- Modify: `src/scripts/backtest_rr_intraday.py`
- Modify: `src/scripts/backtest_cn_b_topology.py`
- Modify: `src/scripts/backtest_signals.py`

**Group 2 — 6 argparse scripts:** change `default=None` → `default=bar_loader.DEFAULT_QUANT_ROOT` only.

- [ ] **Step 1: Update `src/scripts/backtest_fusion.py`** (line 185)

```python
    parser.add_argument("--quant-data-root", type=Path, default=None, dest="quant_data_root",
```
→
```python
    parser.add_argument("--quant-data-root", type=Path, default=bar_loader.DEFAULT_QUANT_ROOT, dest="quant_data_root",
```

- [ ] **Step 2: Update `src/scripts/backtest_fusion_d1h15m.py`** (line 174)

```python
    parser.add_argument("--quant-data-root", type=Path, default=None, dest="quant_data_root",
```
→
```python
    parser.add_argument("--quant-data-root", type=Path, default=bar_loader.DEFAULT_QUANT_ROOT, dest="quant_data_root",
```

- [ ] **Step 3: Update `src/scripts/backtest_b_topology_multi.py`** (line 168)

```python
    parser.add_argument("--quant-data-root", type=Path, default=None, dest="quant_data_root",
```
→
```python
    parser.add_argument("--quant-data-root", type=Path, default=bar_loader.DEFAULT_QUANT_ROOT, dest="quant_data_root",
```

- [ ] **Step 4: Update `src/scripts/backtest_rr_pool.py`** (line 466)

```python
    p.add_argument("--quant-data-root", type=Path, default=None, dest="quant_data_root",
```
→
```python
    p.add_argument("--quant-data-root", type=Path, default=bar_loader.DEFAULT_QUANT_ROOT, dest="quant_data_root",
```

- [ ] **Step 5: Update `src/scripts/backtest_rr_intraday.py`** (line 485)

```python
    p.add_argument("--quant-data-root", type=Path, default=None, dest="quant_data_root",
```
→
```python
    p.add_argument("--quant-data-root", type=Path, default=bar_loader.DEFAULT_QUANT_ROOT, dest="quant_data_root",
```

- [ ] **Step 6: Update `src/scripts/backtest_cn_b_topology.py`** (line 187)

```python
    parser.add_argument("--quant-data-root", type=Path, default=None, dest="quant_data_root",
```
→
```python
    parser.add_argument("--quant-data-root", type=Path, default=bar_loader.DEFAULT_QUANT_ROOT, dest="quant_data_root",
```

**Group 3 — `backtest_signals.py` manual parsing**

- [ ] **Step 7: Update `src/scripts/backtest_signals.py`** (line 252)

```python
    quant_root: Path | None = None
```
→
```python
    quant_root: Path = bar_loader.DEFAULT_QUANT_ROOT
```

- [ ] **Step 8: Run the full test suite**

```bash
cd /Users/huhan/workspace/trading/macd-momentum
python -m pytest src/tests/ -q
```

Expected: `45 passed`

- [ ] **Step 9: Commit**

```bash
cd /Users/huhan/workspace/trading/macd-momentum
git add src/scripts/backtest_fusion.py src/scripts/backtest_fusion_d1h15m.py \
        src/scripts/backtest_b_topology_multi.py src/scripts/backtest_rr_pool.py \
        src/scripts/backtest_rr_intraday.py src/scripts/backtest_cn_b_topology.py \
        src/scripts/backtest_signals.py
git commit -m "feat: use bar_loader.DEFAULT_QUANT_ROOT as default in Group 2+3 scripts"
```
