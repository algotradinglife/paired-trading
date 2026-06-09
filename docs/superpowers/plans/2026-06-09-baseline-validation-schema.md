# Baseline Validation `--full` + Schema v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `validate_baselines.py --full` parse real backtest output and detect DRIFT against stored baselines, and add schema v2 governance fields.

**Architecture:** A shared producer module (`_baseline_output.py`) lets 5 backtests emit a `backtest_output_v1` JSON contract (`--out-json`). `backtest_full_stack.py` emits per-`(lane, symbol)` cells (the primary drift anchor, one run covers all lanes); the 4 K=3 scripts emit fold cells (secondary). The validator runs full_stack once per pass (cached), reconstructs each baseline's anchor by filtering its `full_stack_lane` block to `symbols_included` and n-weighted aggregating, then diffs against the baseline using global tolerance + optional per-baseline `tolerance_policy`. The validator never rewrites baseline JSON.

**Tech Stack:** Python 3, pandas, pytest. Repo root has `src/`; run from `src/` with `.venv/bin/python`. VCS is **jj** (use `jj describe`/`jj new`, not git). Tests live in `src/tests/`, run via `.venv/bin/python -m pytest tests/ -q`.

**Spec:** `docs/superpowers/specs/2026-06-09-baseline-validation-schema-design.md`

---

## File Structure

- **Create** `src/scripts/_baseline_output.py` — producer-side contract: `SCHEMA`, `write_baseline_output`, `compute_data_hash`, `fold_samples_from_period_df`. Imported by the 5 backtests.
- **Create** `src/tests/test_baseline_output.py` — unit tests for the producer module.
- **Create** `src/tests/test_validate_baselines_compare.py` — unit tests for the validator comparison logic.
- **Modify** `src/scripts/validate_baselines.py` — add tolerance defaults, `_resolve_tolerance`, `_aggregate_symbols`, `_compare_cell`, `_compare_against_baseline`; replace `_run_repro` with `_run_and_compare`; cache one full_stack run per pass; propagate `DRIFT_DETECTED` to row status.
- **Modify** `src/scripts/backtest_full_stack.py` — add `--out-json`; emit per-`(lane, symbol)` cells.
- **Modify** `src/scripts/backtest_bpull.py`, `backtest_vflush.py`, `backtest_pa_standalone.py`, `backtest_pa_cn_phasefilter.py` — add `--out-json`; emit `kind:folds`.
- **Modify** the 11 `baselines/*.json` — bump `schema_version` to 2; backfill v2 fields on the 4 in-scope K=3 lanes.
- **Modify** `baselines/README.md` — document schema v2.

---

## Canonical shapes (used across all tasks — keep names exact)

- **cell**: `{"n": int|None, "ev_r": float|None, "win_pct": float|None}`
- **tolerance**: `{"ev_r_abs": float, "sign_flip": bool, "n_pct": float, "win_pct_pp": float|None, "min_n": int}`
- **compare status**: one of `"OK"`, `"WARN"`, `"DRIFT"`
- **output doc**: `{"schema": "backtest_output_v1", "kind": "folds"|"full_stack", ...}`
- **fold keys**: `"is"`, `"f1"`, `"f2"`, `"f3"` (mapped from period labels `IS`/`OOS1`/`OOS2`/`OOS3`)

---

## Task 1: `compute_data_hash` in `_baseline_output.py`

**Files:**
- Create: `src/scripts/_baseline_output.py`
- Test: `src/tests/test_baseline_output.py`

- [ ] **Step 1: Write the failing test**

```python
# src/tests/test_baseline_output.py
import pandas as pd
from scripts._baseline_output import compute_data_hash


def _df(closes):
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=len(closes), tz="UTC"),
        "open": closes, "high": closes, "low": closes,
        "close": closes, "volume": [1] * len(closes),
    })


def test_data_hash_is_deterministic():
    bars = [("cu", _df([1.0, 2.0, 3.0])), ("ag", _df([4.0, 5.0]))]
    assert compute_data_hash(bars) == compute_data_hash(list(reversed(bars)))


def test_data_hash_changes_on_any_row_edit():
    h0 = compute_data_hash([("cu", _df([1.0, 2.0, 3.0]))])
    h1 = compute_data_hash([("cu", _df([1.0, 9.0, 3.0]))])  # middle row changed
    assert h0 != h1


def test_data_hash_changes_on_truncation():
    h0 = compute_data_hash([("cu", _df([1.0, 2.0, 3.0]))])
    h1 = compute_data_hash([("cu", _df([1.0, 2.0]))])
    assert h0 != h1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && .venv/bin/python -m pytest tests/test_baseline_output.py -q`
Expected: FAIL with `ModuleNotFoundError: scripts._baseline_output`

- [ ] **Step 3: Write minimal implementation**

```python
# src/scripts/_baseline_output.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src && .venv/bin/python -m pytest tests/test_baseline_output.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
jj describe -m "feat(baselines): _baseline_output.compute_data_hash" && jj new
```

---

## Task 2: `fold_samples_from_period_df`

**Files:**
- Modify: `src/scripts/_baseline_output.py`
- Test: `src/tests/test_baseline_output.py`

- [ ] **Step 1: Write the failing test**

```python
# append to src/tests/test_baseline_output.py
from scripts._baseline_output import fold_samples_from_period_df


def test_fold_samples_maps_periods_and_computes():
    df = pd.DataFrame({
        "period": ["IS", "IS", "OOS1", "OOS2", "OOS2"],
        "r": [1.0, -1.0, 0.5, 2.0, -1.0],
    })
    out = fold_samples_from_period_df(df)
    assert out["is"] == {"n": 2, "ev_r": 0.0, "win_pct": 50.0}
    assert out["f1"] == {"n": 1, "ev_r": 0.5, "win_pct": 100.0}
    assert out["f2"] == {"n": 2, "ev_r": 0.5, "win_pct": 50.0}
    assert out["f3"] == {"n": None, "ev_r": None, "win_pct": None}  # no OOS3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && .venv/bin/python -m pytest tests/test_baseline_output.py::test_fold_samples_maps_periods_and_computes -q`
Expected: FAIL with `ImportError` / `cannot import name 'fold_samples_from_period_df'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/scripts/_baseline_output.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src && .venv/bin/python -m pytest tests/test_baseline_output.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
jj describe -m "feat(baselines): fold_samples_from_period_df helper" && jj new
```

---

## Task 3: `write_baseline_output`

**Files:**
- Modify: `src/scripts/_baseline_output.py`
- Test: `src/tests/test_baseline_output.py`

- [ ] **Step 1: Write the failing test**

```python
# append to src/tests/test_baseline_output.py
import json
from scripts._baseline_output import write_baseline_output, SCHEMA


def test_write_folds_output(tmp_path):
    p = tmp_path / "out.json"
    write_baseline_output(p, kind="folds", lane="bpull", pool="cn_metal_futures",
                          samples={"is": {"n": 1, "ev_r": 0.1, "win_pct": 100.0}},
                          data_hash="sha256:abc", params_echo={"stop_mult": 1.5})
    doc = json.loads(p.read_text())
    assert doc["schema"] == SCHEMA and doc["kind"] == "folds"
    assert doc["lane"] == "bpull" and doc["samples"]["is"]["n"] == 1


def test_write_full_stack_output(tmp_path):
    p = tmp_path / "fs.json"
    lanes = {"bpull": {"kq_m_shfe_cu": {"n": 17, "ev_r": 0.13, "win_pct": 64.0}}}
    write_baseline_output(p, kind="full_stack", lanes=lanes, data_hash="sha256:def")
    doc = json.loads(p.read_text())
    assert doc["kind"] == "full_stack" and doc["lanes"]["bpull"]["kq_m_shfe_cu"]["n"] == 17


def test_write_rejects_unknown_kind(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        write_baseline_output(tmp_path / "x.json", kind="bogus")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && .venv/bin/python -m pytest tests/test_baseline_output.py -q`
Expected: FAIL with `cannot import name 'write_baseline_output'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/scripts/_baseline_output.py
_KINDS = ("folds", "full_stack")


def write_baseline_output(path, *, kind: str, **payload) -> None:
    """Serialize a backtest_output_v1 doc. payload is the kind-specific body
    (folds: lane/pool/samples/data_hash/params_echo; full_stack: lanes/data_hash)."""
    if kind not in _KINDS:
        raise ValueError(f"unknown kind {kind!r}; expected one of {_KINDS}")
    doc = {"schema": SCHEMA, "kind": kind, **payload}
    Path(path).write_text(json.dumps(doc, indent=2, default=str), encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src && .venv/bin/python -m pytest tests/test_baseline_output.py -q`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
jj describe -m "feat(baselines): write_baseline_output contract writer" && jj new
```

---

## Task 4: Validator tolerance defaults + `_aggregate_symbols`

**Files:**
- Modify: `src/scripts/validate_baselines.py`
- Test: `src/tests/test_validate_baselines_compare.py`

- [ ] **Step 1: Write the failing test**

```python
# src/tests/test_validate_baselines_compare.py
from scripts.validate_baselines import _resolve_tolerance, _aggregate_symbols, GLOBAL_TOLERANCE


def test_resolve_tolerance_uses_global_default():
    assert _resolve_tolerance({})["ev_r_abs"] == GLOBAL_TOLERANCE["ev_r_abs"]


def test_resolve_tolerance_applies_override():
    tol = _resolve_tolerance({"tolerance_policy": {"ev_r_abs": 0.25}})
    assert tol["ev_r_abs"] == 0.25
    assert tol["n_pct"] == GLOBAL_TOLERANCE["n_pct"]  # untouched keys keep default


def test_aggregate_symbols_n_weighted():
    block = {
        "cu": {"n": 10, "ev_r": 0.20, "win_pct": 60.0},
        "sc": {"n": 30, "ev_r": 0.00, "win_pct": 40.0},
        "ag": {"n": 5, "ev_r": -1.0, "win_pct": 0.0},  # excluded below
    }
    cell = _aggregate_symbols(block, ["cu", "sc"])
    assert cell["n"] == 40
    assert cell["ev_r"] == 0.05   # (10*0.20 + 30*0.0)/40
    assert cell["win_pct"] == 45.0  # (10*60 + 30*40)/40


def test_aggregate_symbols_empty_returns_zero_n():
    assert _aggregate_symbols({}, ["cu"]) == {"n": 0, "ev_r": None, "win_pct": None}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && .venv/bin/python -m pytest tests/test_validate_baselines_compare.py -q`
Expected: FAIL with `cannot import name 'GLOBAL_TOLERANCE'`

- [ ] **Step 3: Write minimal implementation**

Add near the top of `validate_baselines.py` (after the existing constants block, around line 68):

```python
GLOBAL_TOLERANCE = {
    "ev_r_abs": 0.10,
    "sign_flip": True,
    "n_pct": 0.25,
    "win_pct_pp": 10.0,
    "min_n": 10,
}


def _resolve_tolerance(b: dict) -> dict:
    tol = dict(GLOBAL_TOLERANCE)
    tol.update(b.get("tolerance_policy") or {})
    return tol


def _aggregate_symbols(lane_block: dict, symbols: list) -> dict:
    """n-weighted aggregate of {symbol: cell} over the given symbols.
    Weighted mean of per-symbol ev_r == overall ev_r (EV is a per-trade mean)."""
    cells = [lane_block[s] for s in symbols
             if s in lane_block and lane_block[s].get("n")]
    total_n = sum(c["n"] for c in cells)
    if total_n == 0:
        return {"n": 0, "ev_r": None, "win_pct": None}
    ev = sum(c["n"] * c["ev_r"] for c in cells) / total_n
    win_cells = [c for c in cells if c.get("win_pct") is not None]
    win_n = sum(c["n"] for c in win_cells)
    win = (sum(c["n"] * c["win_pct"] for c in win_cells) / win_n) if win_n else None
    return {"n": total_n, "ev_r": round(ev, 3),
            "win_pct": round(win, 1) if win is not None else None}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src && .venv/bin/python -m pytest tests/test_validate_baselines_compare.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
jj describe -m "feat(validate): tolerance resolve + n-weighted symbol aggregate" && jj new
```

---

## Task 5: Validator `_compare_cell`

**Files:**
- Modify: `src/scripts/validate_baselines.py`
- Test: `src/tests/test_validate_baselines_compare.py`

- [ ] **Step 1: Write the failing test**

```python
# append to src/tests/test_validate_baselines_compare.py
from scripts.validate_baselines import _compare_cell, _resolve_tolerance

TOL = _resolve_tolerance({})  # global defaults


def _cell(n, ev, win=None):
    return {"n": n, "ev_r": ev, "win_pct": win}


def test_compare_within_tolerance_ok():
    st, _ = _compare_cell(_cell(50, 0.20), _cell(50, 0.25), TOL)
    assert st == "OK"


def test_compare_ev_drift():
    st, d = _compare_cell(_cell(50, 0.20), _cell(50, 0.40), TOL)
    assert st == "DRIFT" and "ev_r" in d


def test_compare_sign_flip_is_drift():
    st, _ = _compare_cell(_cell(50, 0.05), _cell(50, -0.05), TOL)
    assert st == "DRIFT"


def test_compare_n_inflation_drift():
    st, d = _compare_cell(_cell(50, 0.20), _cell(70, 0.20), TOL)
    assert st == "DRIFT" and "n " in d


def test_compare_tiny_n_downgrades_to_warn():
    st, _ = _compare_cell(_cell(6, 0.20), _cell(6, 0.90), TOL)  # ev drift but n<10
    assert st == "WARN"


def test_compare_win_pct_is_warn_only():
    st, _ = _compare_cell(_cell(50, 0.20, 60.0), _cell(50, 0.20, 80.0), TOL)
    assert st == "WARN"


def test_compare_skips_n_pct_when_baseline_n_null():
    st, _ = _compare_cell(_cell(None, 0.20), _cell(99, 0.22), TOL)
    assert st == "OK"  # ev within tol; n_pct skipped (no divide)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && .venv/bin/python -m pytest tests/test_validate_baselines_compare.py -q`
Expected: FAIL with `cannot import name '_compare_cell'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to validate_baselines.py
def _compare_cell(base: dict, now: dict, tol: dict) -> tuple[str, str]:
    """Compare one baseline cell vs emitted cell. Returns (status, detail).
    status in {OK, WARN, DRIFT}. DRIFT downgrades to WARN when baseline n < min_n."""
    issues: list[str] = []
    drift = False
    warn = False

    b_ev, n_ev = base.get("ev_r"), now.get("ev_r")
    if b_ev is not None and n_ev is not None:
        if tol.get("sign_flip") and (b_ev > 0) != (n_ev > 0) and abs(b_ev - n_ev) > 1e-9:
            issues.append(f"ev_r sign flip {b_ev:+.3f}->{n_ev:+.3f}")
            drift = True
        if abs(n_ev - b_ev) > tol["ev_r_abs"]:
            issues.append(f"ev_r {b_ev:+.3f}->{n_ev:+.3f} (d{n_ev - b_ev:+.3f})")
            drift = True

    b_n, n_n = base.get("n"), now.get("n")
    if b_n and n_n is not None:  # skip when baseline n is None/0 (no divide)
        if abs(n_n - b_n) / b_n > tol["n_pct"]:
            issues.append(f"n {b_n}->{n_n} (>{tol['n_pct']:.0%})")
            drift = True

    wp = tol.get("win_pct_pp")
    b_w, n_w = base.get("win_pct"), now.get("win_pct")
    if wp is not None and b_w is not None and n_w is not None and abs(n_w - b_w) > wp:
        issues.append(f"win_pct {b_w:.1f}->{n_w:.1f} (>{wp}pp)")
        warn = True

    if drift and b_n is not None and b_n < tol["min_n"]:
        return "WARN", f"tiny-n(<{tol['min_n']}): " + "; ".join(issues)
    if drift:
        return "DRIFT", "; ".join(issues)
    if warn:
        return "WARN", "; ".join(issues)
    return "OK", "within tolerance"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src && .venv/bin/python -m pytest tests/test_validate_baselines_compare.py -q`
Expected: PASS (11 passed)

- [ ] **Step 5: Commit**

```bash
jj describe -m "feat(validate): _compare_cell drift rules + edge cases" && jj new
```

---

## Task 6: Validator `_compare_against_baseline`

**Files:**
- Modify: `src/scripts/validate_baselines.py`
- Test: `src/tests/test_validate_baselines_compare.py`

- [ ] **Step 1: Write the failing test**

```python
# append to src/tests/test_validate_baselines_compare.py
from scripts.validate_baselines import _compare_against_baseline


def _baseline():
    return {
        "lane": "pa_h2", "pool": "cn_bond",
        "full_stack_lane": "pa_cn_bond",
        "symbols_included": ["tf", "t"],
        "samples_full_stack_5y": {"n": 40, "ev_r": 0.12, "win_pct": 65.0},
        "samples": {"f1": {"n": 16, "ev_r": 0.22, "win_pct": None}},
        "data_snapshot_hash": "sha256:OLD",
    }


def test_primary_anchor_ok():
    fs = {"pa_cn_bond": {"tf": {"n": 20, "ev_r": 0.10, "win_pct": 64.0},
                          "t": {"n": 20, "ev_r": 0.14, "win_pct": 66.0}}}
    status, details = _compare_against_baseline(_baseline(), fs, None)
    assert status == "OK"


def test_primary_anchor_drift():
    fs = {"pa_cn_bond": {"tf": {"n": 20, "ev_r": 0.40, "win_pct": 64.0},
                          "t": {"n": 20, "ev_r": 0.50, "win_pct": 66.0}}}
    status, details = _compare_against_baseline(_baseline(), fs, None)
    assert status == "DRIFT"
    assert any("full_stack" in d for d in details)


def test_fold_secondary_drift():
    fs = {"pa_cn_bond": {"tf": {"n": 20, "ev_r": 0.10, "win_pct": 64.0},
                          "t": {"n": 20, "ev_r": 0.14, "win_pct": 66.0}}}
    fold_emitted = {"samples": {"f1": {"n": 16, "ev_r": 0.80, "win_pct": None}}}
    status, details = _compare_against_baseline(_baseline(), fs, fold_emitted)
    assert status == "DRIFT"
    assert any(d.startswith("f1") for d in details)


def test_data_changed_attribution():
    fs = {"pa_cn_bond": {"tf": {"n": 20, "ev_r": 0.40, "win_pct": 64.0},
                          "t": {"n": 20, "ev_r": 0.50, "win_pct": 66.0}}}
    fold_emitted = {"data_hash": "sha256:NEW"}
    status, details = _compare_against_baseline(_baseline(), fs, fold_emitted)
    assert status == "DRIFT"
    assert any("data changed" in d for d in details)


def test_no_full_stack_lane_skips_primary():
    b = _baseline()
    del b["full_stack_lane"]
    status, details = _compare_against_baseline(b, {}, None)
    assert status == "OK"  # nothing to compare
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && .venv/bin/python -m pytest tests/test_validate_baselines_compare.py -q`
Expected: FAIL with `cannot import name '_compare_against_baseline'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to validate_baselines.py
_FOLD_KEYS = ("is", "f1", "f2", "f3")


def _worst(statuses: list) -> str:
    if "DRIFT" in statuses:
        return "DRIFT"
    if "WARN" in statuses:
        return "WARN"
    return "OK"


def _compare_against_baseline(b: dict, full_stack_map, fold_emitted) -> tuple[str, list]:
    """Returns (status, details). status in {OK, WARN, DRIFT}. Pure; no I/O."""
    tol = _resolve_tolerance(b)
    statuses: list[str] = []
    details: list[str] = []

    # Primary anchor: full_stack[full_stack_lane] filtered to symbols_included
    fsl = b.get("full_stack_lane")
    base_fs = b.get("samples_full_stack_5y")
    if fsl and base_fs and full_stack_map is not None:
        lane_block = full_stack_map.get(fsl, {})
        now = _aggregate_symbols(lane_block, b.get("symbols_included", []))
        st, d = _compare_cell(base_fs, now, tol)
        statuses.append(st)
        details.append(f"full_stack[{fsl}]: {d}")

    # Secondary folds (only cells present + non-null on both sides)
    if fold_emitted and fold_emitted.get("samples"):
        base_samples = b.get("samples", {})
        now_samples = fold_emitted["samples"]
        for key in _FOLD_KEYS:
            bc, nc = base_samples.get(key), now_samples.get(key)
            if not bc or not nc:
                continue
            if bc.get("ev_r") is None or nc.get("ev_r") is None:
                continue
            st, d = _compare_cell(bc, nc, tol)
            statuses.append(st)
            details.append(f"{key}: {d}")

    # data-hash attribution (informational; sharpens drift messages)
    emitted_hash = (fold_emitted or {}).get("data_hash")
    base_hash = b.get("data_snapshot_hash")
    if emitted_hash and base_hash and emitted_hash != base_hash:
        verb = "data changed -> re-baseline" if "DRIFT" in statuses else "data changed (no drift)"
        details.append(verb)

    return _worst(statuses), details
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src && .venv/bin/python -m pytest tests/test_validate_baselines_compare.py -q`
Expected: PASS (16 passed)

- [ ] **Step 5: Commit**

```bash
jj describe -m "feat(validate): _compare_against_baseline (primary+folds+hash)" && jj new
```

---

## Task 7: Replace `_run_repro` with `_run_and_compare` + full_stack caching + `--full` wiring

**Files:**
- Modify: `src/scripts/validate_baselines.py` (`_run_repro` at lines 180-208; `main` `--full` block at lines 302-306; strict accounting at 338-341)
- Test: `src/tests/test_validate_baselines_compare.py`

- [ ] **Step 1: Write the failing test** (uses a fake full_stack map + fake emitted folds, no subprocess)

```python
# append to src/tests/test_validate_baselines_compare.py
from scripts.validate_baselines import _runtime_status


def test_runtime_status_ok_within_tolerance():
    b = _baseline()
    fs = {"pa_cn_bond": {"tf": {"n": 20, "ev_r": 0.10, "win_pct": 64.0},
                          "t": {"n": 20, "ev_r": 0.14, "win_pct": 66.0}}}
    status, _ = _runtime_status(b, full_stack_map=fs, fold_emitted=None)
    assert status == "OK"


def test_runtime_status_drift_flags_DRIFT_DETECTED():
    b = _baseline()
    fs = {"pa_cn_bond": {"tf": {"n": 20, "ev_r": 0.90, "win_pct": 64.0},
                          "t": {"n": 20, "ev_r": 0.90, "win_pct": 66.0}}}
    status, detail = _runtime_status(b, full_stack_map=fs, fold_emitted=None)
    assert status == "DRIFT_DETECTED"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && .venv/bin/python -m pytest tests/test_validate_baselines_compare.py -q`
Expected: FAIL with `cannot import name '_runtime_status'`

- [ ] **Step 3: Write minimal implementation**

Add `_runtime_status` (maps compare result to a row status string) and a full_stack runner. Add `"DRIFT_DETECTED"` to `STATUS_ICONS` and `STRICT_FAIL_STATUSES`.

```python
# in validate_baselines.py
STATUS_ICONS["DRIFT_DETECTED"] = "[DRFT]"
STRICT_FAIL_STATUSES.add("DRIFT_DETECTED")


def _runtime_status(b: dict, *, full_stack_map, fold_emitted) -> tuple[str, str]:
    """Map a comparison to a row-status string used by the table + --strict."""
    status, details = _compare_against_baseline(b, full_stack_map, fold_emitted)
    detail = "; ".join(details) if details else "no comparable cells"
    if status == "DRIFT":
        return "DRIFT_DETECTED", detail
    if status == "WARN":
        return "WARN", detail
    return "OK", detail


def _run_full_stack_once(timeout: int = 600):
    """Run backtest_full_stack.py --out-json once; return (lanes_map, data_hash) or (None, None)."""
    import shlex, subprocess, tempfile, os
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    tmp.close()
    cmd = f".venv/bin/python scripts/backtest_full_stack.py --out-json {tmp.name}"
    try:
        proc = subprocess.run(shlex.split(cmd), cwd=str(REPO_ROOT / "src"),
                              capture_output=True, text=True, timeout=timeout, check=False)
        if proc.returncode != 0:
            return None, None
        doc = json.loads(pathlib.Path(tmp.name).read_text())
        return doc.get("lanes"), doc.get("data_hash")
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return None, None
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def _run_fold_repro(b: dict):
    """Run the baseline's K=3 repro_command with --out-json; return parsed doc or None."""
    import shlex, subprocess, tempfile, os
    cmd = b.get("repro_command", "")
    if not cmd or not b.get("repro_emits_json"):
        return None
    cwd = REPO_ROOT
    if cmd.startswith("cd src && "):
        cwd = REPO_ROOT / "src"
        cmd = cmd[len("cd src && "):]
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    tmp.close()
    cmd = f"{cmd} --out-json {tmp.name}"
    try:
        proc = subprocess.run(shlex.split(cmd), cwd=str(cwd), capture_output=True,
                              text=True, timeout=300, check=False)
        if proc.returncode != 0:
            return None
        return json.loads(pathlib.Path(tmp.name).read_text())
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return None
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
```

Then rewrite the `--full` block in `main()`. Replace lines 302-306:

```python
        row = _audit(b, f)
        if args.full and row["status"] != "BROKEN":
            fold_emitted = _run_fold_repro(b)
            rstatus, rdetail = _runtime_status(
                b, full_stack_map=_FULL_STACK_CACHE["lanes"], fold_emitted=fold_emitted)
            row["repro_status"] = rstatus
            row["repro_msg"] = rdetail
            if rstatus == "DRIFT_DETECTED":
                row["status"] = "DRIFT_DETECTED"   # propagate so --strict catches it
                row["reason"] = f"runtime drift: {rdetail[:100]}"
        results.append(row)
```

Add the full_stack cache near the top of `main()` (after `results: list[dict] = []`):

```python
    _FULL_STACK_CACHE = {"lanes": None}
    if args.full:
        lanes, _fs_hash = _run_full_stack_once()
        _FULL_STACK_CACHE["lanes"] = lanes
        if lanes is None:
            print("warning: full_stack run failed/timed out — primary-anchor checks "
                  "skipped (no false DRIFT)", file=sys.stderr)
```

(`_FULL_STACK_CACHE` is a local dict so the `--full` block can read it; keep both edits inside `main`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src && .venv/bin/python -m pytest tests/test_validate_baselines_compare.py -q`
Expected: PASS (18 passed)

- [ ] **Step 5: Run the existing default-mode validator to confirm no regression**

Run: `cd src && .venv/bin/python scripts/validate_baselines.py`
Expected: same table as before (metadata mode unchanged), exit 0/1 as before.

- [ ] **Step 6: Commit**

```bash
jj describe -m "feat(validate): --full real parse + drift detection + strict propagation" && jj new
```

---

## Task 8: Wire `backtest_full_stack.py --out-json`

**Files:**
- Modify: `src/scripts/backtest_full_stack.py` (add arg near line 537; emit after `df` built, around line 562)

- [ ] **Step 1: Add the `--out-json` argument**

After line 538 (`--out-csv` arg) add:

```python
    p.add_argument("--out-json", type=Path, default=None,
                   help="Write backtest_output_v1 per-(lane,symbol) JSON for "
                        "validate_baselines.py --full")
```

- [ ] **Step 2: Emit per-(lane, symbol) cells**

After the `df` is built and CSV written (after line 562, before `agg = aggregate(df)`), add:

```python
    if args.out_json is not None and not df.empty:
        from scripts._baseline_output import write_baseline_output
        ls = df.groupby(["lane", "symbol"]).agg(
            n=("realized_r", "size"),
            ev_r=("realized_r", "mean"),
            win_pct=("realized_r", lambda s: (s > 0).mean() * 100),
        ).round(3)
        lanes: dict[str, dict] = {}
        for (lane, symbol), r in ls.iterrows():
            lanes.setdefault(lane, {})[symbol] = {
                "n": int(r["n"]), "ev_r": float(r["ev_r"]),
                "win_pct": round(float(r["win_pct"]), 1),
            }
        write_baseline_output(args.out_json, kind="full_stack", lanes=lanes,
                              data_hash=None)  # data_hash wired in Task 8b if needed
        print(f"\nWrote backtest_output_v1 → {args.out_json}")
```

- [ ] **Step 3: Smoke-run on one pool**

Run: `cd src && .venv/bin/python scripts/backtest_full_stack.py --pool CN_BOND --out-json /tmp/fs.json`
Expected: prints "Wrote backtest_output_v1 → /tmp/fs.json"; file has `{"schema":"backtest_output_v1","kind":"full_stack","lanes":{...}}` with at least `pa_cn_bond` populated.

- [ ] **Step 4: Verify the JSON shape**

Run: `cd src && .venv/bin/python -c "import json;d=json.load(open('/tmp/fs.json'));print(d['kind']);print(list(d['lanes']))"`
Expected: `full_stack` then a list of lane labels.

- [ ] **Step 5: Commit**

```bash
jj describe -m "feat(full_stack): --out-json per-(lane,symbol) anchor output" && jj new
```

---

## Task 9: Wire `backtest_bpull.py --out-json`

**Files:**
- Modify: `src/scripts/backtest_bpull.py` (arg near line 150; emit after the trades DataFrame is built, near the fold-print loop at lines 222-239)

- [ ] **Step 1: Add the `--out-json` argument**

After the `--cutoff3` arg (line 151) add:

```python
    parser.add_argument("--out-json", type=Path, default=None,
                        help="Write backtest_output_v1 folds JSON")
    parser.add_argument("--out-lane", default="bpull")
    parser.add_argument("--out-pool", default="cn_metal_futures")
```

- [ ] **Step 2: Emit folds after the trades DataFrame is built**

Locate the trades DataFrame that has `period` and `r` columns (the one the fold-print loop at lines ~222-239 iterates; call it `<df>`). Immediately after it is finalized (and after `k3` is known), add:

```python
    if args.out_json is not None:
        from scripts._baseline_output import (
            write_baseline_output, fold_samples_from_period_df, compute_data_hash)
        samples = fold_samples_from_period_df(<df>)  # <df> = trades frame w/ period,r
        write_baseline_output(
            args.out_json, kind="folds", lane=args.out_lane, pool=args.out_pool,
            samples=samples, data_hash=compute_data_hash(_loaded_bars),
            params_echo={"stop_mult": args.stop_mult, "h_filter": "opposing"})
        print(f"Wrote backtest_output_v1 → {args.out_json}")
```

To populate `_loaded_bars`: find where the script loads daily bars per symbol (the loop that calls `_load`/`load_bars_quant_or_json`). Accumulate them: initialize `_loaded_bars = []` before that loop, and append `(_sym, _daily_df)` inside it. (If wiring data_hash is awkward in this script, pass `data_hash=None` — the validator treats a missing hash as "no attribution", which is acceptable; folds still compare.)

- [ ] **Step 3: Smoke-run**

Run: `cd src && .venv/bin/python scripts/backtest_bpull.py --pool CN_METAL --cutoff3 2025-06-30 --out-json /tmp/bpull.json`
Expected: human stdout unchanged + "Wrote backtest_output_v1 → /tmp/bpull.json"; file `kind:folds` with `samples.f1/f2/f3` populated.

- [ ] **Step 4: Verify**

Run: `cd src && .venv/bin/python -c "import json;d=json.load(open('/tmp/bpull.json'));print(d['kind'],d['lane'],list(d['samples']))"`
Expected: `folds bpull ['is','f1','f2','f3']`

- [ ] **Step 5: Commit**

```bash
jj describe -m "feat(bpull): --out-json folds output" && jj new
```

---

## Task 10: Wire `backtest_vflush.py --out-json`

**Files:**
- Modify: `src/scripts/backtest_vflush.py` (arg near line 156; emit near fold output after line 232)

- [ ] **Step 1: Add args** — after `--h-opp-only` (line 158):

```python
    parser.add_argument("--out-json", type=Path, default=None)
    parser.add_argument("--out-lane", default="vflush")
    parser.add_argument("--out-pool", default="cn_metal_futures")
```

- [ ] **Step 2: Emit folds** — after the trades DataFrame (with `period`,`r`) is built, mirror Task 9 Step 2 exactly, using `params_echo={"stop_mult": args.stop_mult, "h_opp_only": args.h_opp_only}`. Accumulate `_loaded_bars` the same way (append `(sym, daily)` where the script loads bars).

- [ ] **Step 3: Smoke-run**

Run: `cd src && .venv/bin/python scripts/backtest_vflush.py --h-opp-only --cutoff3 2025-06-30 --out-json /tmp/vflush.json`
Expected: "Wrote backtest_output_v1 → /tmp/vflush.json"; `kind:folds`, lane `vflush`.

- [ ] **Step 4: Verify**

Run: `cd src && .venv/bin/python -c "import json;d=json.load(open('/tmp/vflush.json'));print(d['kind'],d['lane'])"`
Expected: `folds vflush`

- [ ] **Step 5: Commit**

```bash
jj describe -m "feat(vflush): --out-json folds output" && jj new
```

---

## Task 11: Wire `backtest_pa_standalone.py --out-json`

**Files:**
- Modify: `src/scripts/backtest_pa_standalone.py` (arg near line 162; emit near fold output after line 248)

- [ ] **Step 1: Add args** — after `--isolation-lookback` (line 163):

```python
    parser.add_argument("--out-json", type=Path, default=None)
    parser.add_argument("--out-lane", default="pa_h2_climax")
    parser.add_argument("--out-pool", default="cn_agri_pos")
```

- [ ] **Step 2: Emit folds** — after the trades DataFrame (with `period`,`r`; the one feeding `subset["r"].mean()` at line 245) is built, mirror Task 9 Step 2, `params_echo={"stop_mult": args.stop_mult, "isolation_lookback": args.isolation_lookback}`. Accumulate `_loaded_bars`.

- [ ] **Step 3: Smoke-run**

Run: `cd src && .venv/bin/python scripts/backtest_pa_standalone.py --pool CN_AGRI_POS --stop-mult 1.5 --cutoff3 2024-12-31 --out-json /tmp/pastd.json`
Expected: "Wrote backtest_output_v1 → /tmp/pastd.json"; `kind:folds`, lane `pa_h2_climax`.

- [ ] **Step 4: Verify**

Run: `cd src && .venv/bin/python -c "import json;d=json.load(open('/tmp/pastd.json'));print(d['kind'],d['lane'])"`
Expected: `folds pa_h2_climax`

- [ ] **Step 5: Commit**

```bash
jj describe -m "feat(pa_standalone): --out-json folds output" && jj new
```

---

## Task 12: Wire `backtest_pa_cn_phasefilter.py --out-json`

**Files:**
- Modify: `src/scripts/backtest_pa_cn_phasefilter.py` (arg near line 98; emit in/after `_report` at lines 158-205)

Note: this script reports per pool. The `--out-json` cell should be the **OOS / h=opp** trades for the requested `--pool`, keyed to the matching lane. Map: `--pool CN_BOND` → lane `pa_h2`, pool `cn_bond`; `--pool CN_COMMODITY`/`CN_FUTURES` → lane `pa_h2`, the corresponding baseline pool.

- [ ] **Step 1: Add args** — after the `--pool` arg (line 98):

```python
    parser.add_argument("--out-json", type=Path, default=None)
    parser.add_argument("--out-lane", default="pa_h2")
    parser.add_argument("--out-pool", default=None,
                        help="baseline pool label; defaults to lowercased --pool")
```

- [ ] **Step 2: Build a period-labelled frame and emit**

This script splits folds via `_fold_str`/OOS subsets rather than a single `period` column. After the per-pool h=opp signals frame is available (the `sub`/`oos_sub` data used at lines 171-205), construct a period column from the fold cutoffs and emit. Add a helper inside the script:

```python
def _period_label(ts, c1, c2, c3):
    if ts <= c1: return "IS"
    if ts <= c2: return "OOS1"
    if c3 is not None and ts <= c3: return "OOS2"
    return "OOS3" if c3 is not None else "OOS2"
```

Then where the h=opp signals DataFrame for the pool exists (call it `<sig_df>` with a timestamp column `<ts_col>` and realized-R column `<r_col>`), add at the end of `main()`:

```python
    if args.out_json is not None:
        from scripts._baseline_output import write_baseline_output, fold_samples_from_period_df
        frame = <sig_df>.copy()
        frame["period"] = frame[<ts_col>].apply(
            lambda t: _period_label(pd.Timestamp(t), CUT1, CUT2, CUT3))
        samples = fold_samples_from_period_df(frame, r_col="<r_col>")
        write_baseline_output(args.out_json, kind="folds",
                              lane=args.out_lane,
                              pool=args.out_pool or args.pool.lower(),
                              samples=samples, data_hash=None,
                              params_echo={"h_filter": "opposing", "stop_mult": STOP_MULT})
        print(f"Wrote backtest_output_v1 → {args.out_json}")
```

Replace `<sig_df>`, `<ts_col>`, `<r_col>`, `CUT1/CUT2/CUT3` with the script's actual variables (the OOS h=opp frame and the cutoff Timestamps used in `_report`).

- [ ] **Step 3: Smoke-run**

Run: `cd src && .venv/bin/python scripts/backtest_pa_cn_phasefilter.py --pool CN_BOND --out-json /tmp/phase.json`
Expected: "Wrote backtest_output_v1 → /tmp/phase.json"; `kind:folds`, lane `pa_h2`, pool `cn_bond`.

- [ ] **Step 4: Verify**

Run: `cd src && .venv/bin/python -c "import json;d=json.load(open('/tmp/phase.json'));print(d['kind'],d['lane'],d['pool'])"`
Expected: `folds pa_h2 cn_bond`

- [ ] **Step 5: Commit**

```bash
jj describe -m "feat(phasefilter): --out-json folds output" && jj new
```

---

## Task 13: Backfill the 4 in-scope K=3 baselines to schema v2

**Files (Modify):**
- `baselines/bpull_cn_metal_futures.json`
- `baselines/vflush_cn_metal_cu_sc.json`
- `baselines/pa_h2_cn_bond.json`
- `baselines/pa_h2_cn_futures.json`
- `baselines/pa_h2_cn_metal_futures.json`
- `baselines/pa_h2_climax_cn_agri_pos.json`

- [ ] **Step 1: Add v2 fields to each.** For each file set `"schema_version": 2` and add (use the `full_stack_lane` per the map below; keep existing `symbols_included` as-is — it is the symbol filter):

| baseline file | full_stack_lane |
|---|---|
| bpull_cn_metal_futures.json | `bpull` |
| vflush_cn_metal_cu_sc.json | `vflush` |
| pa_h2_cn_bond.json | `pa_cn_bond` |
| pa_h2_cn_futures.json | `pa_h2` |
| pa_h2_cn_metal_futures.json | `pa_h2` |
| pa_h2_climax_cn_agri_pos.json | `pa_h2_climax` |

Add to each:

```jsonc
  "schema_version": 2,
  "repro_emits_json": true,
  "full_stack_lane": "<from table>",
  "production_binding": [
    "src/engine/divergence/pa_detector.py::policy_weight"
  ],
  "fold_date_ranges": {
    "is": ["2019-01-01", "2022-12-31"],
    "f1": ["2023-01-01", "2024-06-30"],
    "f2": ["2024-07-01", "2025-06-30"],
    "f3": ["2025-07-01", "2025-12-31"]
  },
```

(Use each script's actual `--cutoff1/2/3` defaults for `fold_date_ranges`: bpull/vflush/pa_standalone cutoffs are `2022-12-31 / 2024-06-30 / 2025-06-30` or `2024-12-31`; set the ranges to match that file's repro_command cutoffs. For tiny-n folds, optionally add `"tolerance_policy": {"min_n": 10}` — already the default, so only add an override if widening.)

- [ ] **Step 2: Validate JSON parses**

Run: `cd src && .venv/bin/python -c "import json,glob; [json.load(open(f)) for f in glob.glob('../baselines/*.json')]; print('all parse')"`
Expected: `all parse`

- [ ] **Step 3: Run the metadata validator (no regression)**

Run: `cd src && .venv/bin/python scripts/validate_baselines.py`
Expected: table prints; no new BROKEN rows from the schema bump.

- [ ] **Step 4: Commit**

```bash
jj describe -m "chore(baselines): backfill 4 K=3 lanes to schema v2" && jj new
```

---

## Task 14: Bump remaining 7 baselines + update README + REQUIRED_FIELDS

**Files (Modify):**
- The other 7 `baselines/*.json` (context_a ×2, pa_h2_us_equity, pa_us_60min_us_equity, us_regime_gate, and any not in Task 13)
- `baselines/README.md`
- `src/scripts/validate_baselines.py` (`REQUIRED_FIELDS` at lines 38-42 — do NOT add the new optional fields as required)

- [ ] **Step 1:** Set `"schema_version": 2` on the remaining 7; add `production_binding` where the binding is obvious from the existing notes. Do NOT add `repro_emits_json` (they stay exit-code-only). For lanes with a clean full_stack representation (context_a → `context_a`, pa_h2_us_equity → `pa_us_dif_pos`, pa_us_60min → `pa_us_60min`) optionally add `full_stack_lane` so they get a primary-anchor check even without fold parsing; `us_regime_gate` omits it.

- [ ] **Step 2:** Update `baselines/README.md` Schema section to document v2 fields (`tolerance_policy`, `fold_date_ranges`, `production_binding`, `data_snapshot_hash`, `full_stack_lane`, `repro_emits_json`) and the global tolerance defaults (`ev_r ±0.10R / sign-flip / n ±25% → DRIFT; win_pct ±10pp → WARN; min_n 10`).

- [ ] **Step 3:** Confirm `REQUIRED_FIELDS` still lists only v1 fields (new v2 fields are optional → v1 files keep validating).

- [ ] **Step 4: Validate + run**

Run: `cd src && .venv/bin/python scripts/validate_baselines.py`
Expected: all 11 audited, no new BROKEN.

- [ ] **Step 5: Commit**

```bash
jj describe -m "chore(baselines): schema v2 bump for remaining lanes + README" && jj new
```

---

## Task 15: End-to-end `--full` verification (manual, slow)

**Files:** none (verification only)

- [ ] **Step 1: Run the full validator with parsing**

Run: `cd src && .venv/bin/python scripts/validate_baselines.py --full`
Expected: full_stack runs once (may take minutes); the 4 K=3 lanes also run their fold repro; each row shows a `repro:` line with `OK` / `DRIFT_DETECTED` / `WARN`; lanes without `repro_emits_json` show no fold parse but get a primary-anchor line if `full_stack_lane` is set.

- [ ] **Step 2: Confirm `--strict` exit code reflects drift**

Run: `cd src && .venv/bin/python scripts/validate_baselines.py --full --strict; echo "exit=$?"`
Expected: `exit=0` if no DRIFT_DETECTED; `exit=1` if any lane drifts (and the drift row is visible).

- [ ] **Step 3: Backfill `data_snapshot_hash`** from the first clean run: for each of the 4 K=3 baselines (and any with `full_stack_lane`), set `data_snapshot_hash` to the `data_hash` emitted by that run, so future runs can attribute drift to data vs code.

- [ ] **Step 4: Run the whole unit suite**

Run: `cd src && .venv/bin/python -m pytest tests/ -q`
Expected: all pass (existing 441 + new baseline_output + validate_baselines_compare tests).

- [ ] **Step 5: Final commit**

```bash
jj describe -m "chore(baselines): backfill data_snapshot_hash from first --full run" && jj new
```

---

## Self-review notes (for the implementer)

- The 4 K=3 scripts share an identical period→fold pattern; `fold_samples_from_period_df` is the single source — do not re-implement per script.
- `data_hash` wiring in the K=3 scripts is best-effort: if accumulating `_loaded_bars` is awkward in a given script, pass `data_hash=None`. Folds still compare; only the data-vs-code attribution is lost for that lane.
- Never auto-edit a baseline's `verdict` — runtime drift is reported, the human owns the verdict.
- Field names are exact: cells are `{n, ev_r, win_pct}`; full_stack normalizes pandas `ev_R`/`win_rate` to `ev_r`/`win_pct` at emit time (Task 8 Step 2 already uses `ev_r`/`win_pct` agg names).
