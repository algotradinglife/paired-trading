"""Audit `baselines/*.json` baseline artifacts.

Modes (mutually compatible):
  default (metadata)  — fast scan: expiry / verdict / staleness / schema
  --full              — run backtest_full_stack.py once and diff each baseline's
                        full_stack primary anchor (samples_full_stack_5y) against
                        the live replay; slow but runs the full stack only once
  --strict            — exit non-zero on STALE, DRIFT, EXPIRED, BROKEN, or
                        registry mismatches. Use in CI/cron.

Registry check (always on):
  baselines/EXPECTED_LANES.json lists (lane, pool) pairs production currently
  emits. Anything in `expected` missing from filesystem → BROKEN.
  Anything on filesystem not in `expected`+`pending` → WARN (orphan).

A baseline file is the single source of truth for "what evidence backs this
lane × pool's policy_weight". Detector docstrings should REF the JSON, not
inline numbers.

Usage:
    python scripts/validate_baselines.py
    python scripts/validate_baselines.py --strict
    python scripts/validate_baselines.py --full
    python scripts/validate_baselines.py --lane pa_h2_climax
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
BASELINES_DIR = REPO_ROOT / "baselines"
REGISTRY_PATH = BASELINES_DIR / "EXPECTED_LANES.json"

REQUIRED_FIELDS = (
    "schema_version", "lane", "pool", "verdict",
    "policy_weight_assigned", "valid_until", "commit_hash",
    "data_snapshot", "last_verified",
)

VERDICTS = {
    "STRONG PASS", "PASS", "CONDITIONAL PASS",
    "marginal", "REJECT", "STALE", "DRIFT",
    # Production-active but no formal K=3 walk-forward (imported from docstring).
    # Treated as a production gap under --strict.
    "PENDING_VALIDATION",
    # Meta-gate / non-lane component that's been deployed with calibration
    # evidence but doesn't follow the K=3 walk-forward shape.
    "DEPLOYED",
}

STATUS_ICONS = {
    "OK":             "[ OK ]",
    "WARN":           "[WARN]",
    "EXPIRED":        "[XPRD]",
    "STALE":          "[STAL]",
    "DRIFT":          "[DRFT]",
    "DRIFT_DETECTED": "[DRFT]",
    "PENDING":        "[PEND]",
    "BROKEN":         "[BRKN]",
    "MISSING":        "[MISS]",
    "ORPHAN":         "[ORPH]",
}

# Status classes treated as failures under --strict
STRICT_FAIL_STATUSES = {"BROKEN", "EXPIRED", "STALE", "DRIFT", "DRIFT_DETECTED", "PENDING", "MISSING"}

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
    if not isinstance(symbols, list):
        return {"n": 0, "ev_r": None, "win_pct": None}
    # Case-insensitive symbol match: backtest_full_stack emits US tickers
    # uppercase (QQQ) while baselines list them lowercase (qqq).
    ci = {k.lower(): v for k, v in lane_block.items()}
    cells = [ci[s.lower()] for s in symbols
             if s.lower() in ci and ci[s.lower()].get("n")]
    total_n = sum(c["n"] for c in cells)
    if total_n == 0:
        return {"n": 0, "ev_r": None, "win_pct": None}
    ev = sum(c["n"] * c["ev_r"] for c in cells) / total_n
    win_cells = [c for c in cells if c.get("win_pct") is not None]
    win_n = sum(c["n"] for c in win_cells)
    win = (sum(c["n"] * c["win_pct"] for c in win_cells) / win_n) if win_n else None
    return {"n": total_n, "ev_r": round(ev, 3),
            "win_pct": round(win, 1) if win is not None else None}


def _compare_cell(base: dict, now: dict, tol: dict) -> tuple[str, str]:
    """Compare one baseline cell vs emitted cell. Returns (status, detail).
    status in {OK, WARN, DRIFT}. DRIFT downgrades to WARN when baseline n < min_n."""
    issues: list[str] = []
    drift = False
    warn = False

    b_ev, n_ev = base.get("ev_r"), now.get("ev_r")
    if b_ev is not None and n_ev is not None:
        if tol.get("sign_flip") and ((b_ev > 0 and n_ev < 0) or (b_ev < 0 and n_ev > 0)):
            issues.append(f"ev_r sign flip {b_ev:+.3f}->{n_ev:+.3f}")
            drift = True
        if abs(n_ev - b_ev) > tol["ev_r_abs"]:
            issues.append(f"ev_r {b_ev:+.3f}->{n_ev:+.3f} (d{n_ev - b_ev:+.3f})")
            drift = True

    b_n, n_n = base.get("n"), now.get("n")
    if b_n and n_n is not None:
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


def _worst(statuses: list) -> str:
    if "DRIFT" in statuses:
        return "DRIFT"
    if "WARN" in statuses:
        return "WARN"
    return "OK"


def _compare_against_baseline(b: dict, full_stack_map, emitted_data_hash=None) -> tuple[str, list]:
    """Returns (status, details). status in {OK, WARN, DRIFT}. Pure; no I/O."""
    tol = _resolve_tolerance(b)
    statuses: list[str] = []
    details: list[str] = []

    fsl = b.get("full_stack_lane")
    base_fs = b.get("samples_full_stack_5y")
    if fsl and base_fs and full_stack_map is not None:
        lane_block = full_stack_map.get(fsl, {})
        now = _aggregate_symbols(lane_block, b.get("symbols_included", []))
        st, d = _compare_cell(base_fs, now, tol)
        statuses.append(st)
        details.append(f"full_stack[{fsl}]: {d}")

    emitted_hash = emitted_data_hash
    base_hash = b.get("data_snapshot_hash")
    if emitted_hash and base_hash and emitted_hash != base_hash:
        verb = "data changed -> re-baseline" if "DRIFT" in statuses else "data changed (no drift)"
        details.append(verb)

    return _worst(statuses), details


def _runtime_status(b: dict, *, full_stack_map, emitted_data_hash=None) -> tuple[str, str]:
    """Map a comparison to a row-status string used by the table + --strict."""
    status, details = _compare_against_baseline(b, full_stack_map, emitted_data_hash)
    detail = "; ".join(details) if details else "no comparable cells"
    if status == "DRIFT":
        return "DRIFT_DETECTED", detail
    if status == "WARN":
        return "WARN", detail
    return "OK", detail


def _run_full_stack_once(timeout: int = 600):
    """Run backtest_full_stack.py --out-json once; return (lanes_map, data_hash) or (None, None)."""
    import shlex
    import subprocess
    import tempfile
    import os

    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    tmp.close()
    cmd = f".venv/bin/python scripts/backtest_full_stack.py --out-json {tmp.name}"
    try:
        proc = subprocess.run(
            shlex.split(cmd),
            cwd=str(REPO_ROOT / "src"),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
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



def _today() -> dt.date:
    return dt.date.today()


def _load(p: pathlib.Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _check_schema(b: dict) -> list[str]:
    issues = []
    for f in REQUIRED_FIELDS:
        if f not in b:
            issues.append(f"missing field: {f}")
    if b.get("verdict") not in VERDICTS:
        issues.append(f"unknown verdict: {b.get('verdict')!r}")
    samples = b.get("samples", {})
    for fold, s in samples.items():
        if not isinstance(s, dict):
            issues.append(f"samples.{fold} is not a dict")
            continue
        n = s.get("n")
        ev = s.get("ev_r")
        if ev is not None and not isinstance(ev, (int, float)):
            issues.append(f"samples.{fold}.ev_r non-numeric")
        if n is not None and not isinstance(n, int):
            issues.append(f"samples.{fold}.n non-int")
    return issues


def _check_freshness(b: dict) -> tuple[str, str]:
    try:
        valid_until = dt.date.fromisoformat(b["valid_until"])
    except (KeyError, ValueError):
        return "WARN", "valid_until missing/malformed"
    today = _today()
    days = (valid_until - today).days
    if days < 0:
        return "EXPIRED", f"expired {-days}d ago (valid_until={valid_until})"
    if days < 14:
        return "WARN", f"expires in {days}d"
    return "OK", f"valid for {days}d"


def _check_assigned_vs_recommended(b: dict) -> tuple[bool, str]:
    """Return (is_consistent, reason). Catches assigned > recommended drift gap."""
    assigned = b.get("policy_weight_assigned")
    recommended = b.get("policy_weight_recommended")
    if recommended is None:
        return True, ""
    if assigned is None or assigned == recommended:
        return True, ""
    return False, (
        f"policy_weight_assigned={assigned} != recommended={recommended} "
        f"(production gap)"
    )


def _audit(b: dict, source: pathlib.Path) -> dict:
    issues = _check_schema(b)
    status, reason = _check_freshness(b)

    verdict = b.get("verdict", "UNKNOWN")
    weight = b.get("policy_weight_assigned", None)
    lane = b.get("lane", "?")
    pool = b.get("pool", "?")

    if verdict == "STALE":
        status = "STALE"
        reason = "verdict=STALE (known broken)"
    elif verdict == "DRIFT":
        status = "DRIFT"
        consistent, mismatch_reason = _check_assigned_vs_recommended(b)
        if not consistent:
            reason = f"verdict=DRIFT; {mismatch_reason}"
        else:
            recommended = b.get("policy_weight_recommended")
            reason = (f"verdict=DRIFT; assigned==recommended={recommended} "
                      f"(weight bumped to recommended; investigation pending)")
    elif verdict == "PENDING_VALIDATION":
        status = "PENDING"
        reason = f"verdict=PENDING_VALIDATION; weight={weight} (no K=3 baseline)"
    elif issues:
        status = "BROKEN"
        reason = f"schema: {issues[0]}"

    # Sanity: STALE/REJECT must not assign a non-zero live weight
    if verdict in {"STALE", "REJECT"} and (weight or 0) > 0:
        status = "BROKEN"
        reason = f"verdict={verdict} but policy_weight={weight} (>0)"

    # Sanity: any verdict with assigned > recommended is a production gap
    if verdict not in {"STALE", "REJECT"}:
        consistent, mismatch_reason = _check_assigned_vs_recommended(b)
        if not consistent and status not in {"BROKEN", "STALE"}:
            status = "BROKEN"
            reason = mismatch_reason

    return {
        "source": source.name,
        "lane": lane,
        "pool": pool,
        "verdict": verdict,
        "weight": weight,
        "status": status,
        "reason": reason,
        "issues": issues,
    }



def _load_registry() -> dict | None:
    if not REGISTRY_PATH.exists():
        return None
    try:
        return _load(REGISTRY_PATH)
    except json.JSONDecodeError:
        return None


def _audit_registry(registry: dict, present_files: set[str]) -> list[dict]:
    """Cross-check filesystem vs EXPECTED_LANES registry. Returns extra rows."""
    rows = []
    expected = registry.get("expected", [])
    pending = registry.get("pending", [])
    expected_files = {e["baseline_file"] for e in expected if "baseline_file" in e}
    pending_files = {p["baseline_file"] for p in pending if "baseline_file" in p}
    known_files = expected_files | pending_files

    # MISSING: expected but not on disk
    for entry in expected:
        bf = entry.get("baseline_file")
        if bf and bf not in present_files:
            rows.append({
                "source": bf,
                "lane": entry.get("lane", "?"),
                "pool": entry.get("pool", "?"),
                "verdict": "REGISTERED",
                "weight": None,
                "status": "MISSING",
                "reason": "registered in EXPECTED_LANES but baseline file not found",
                "issues": [],
            })

    # ORPHAN: on disk but not in expected/pending
    for f in sorted(present_files):
        if f == "EXPECTED_LANES.json" or f == "README.md":
            continue
        if f not in known_files:
            rows.append({
                "source": f,
                "lane": "?",
                "pool": "?",
                "verdict": "?",
                "weight": None,
                "status": "ORPHAN",
                "reason": "file present but not listed in EXPECTED_LANES (expected or pending)",
                "issues": [],
            })

    return rows


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--lane", help="only audit baselines whose lane matches")
    p.add_argument("--full", action="store_true",
                   help="run backtest_full_stack once and diff each baseline's full_stack primary anchor (slow)")
    p.add_argument("--strict", action="store_true",
                   help="exit non-zero on STALE/DRIFT/EXPIRED/BROKEN/MISSING")
    p.add_argument("--json", action="store_true",
                   help="emit machine-readable JSON instead of table")
    args = p.parse_args()

    if not BASELINES_DIR.exists():
        print(f"error: {BASELINES_DIR} does not exist", file=sys.stderr)
        return 2

    files = sorted(BASELINES_DIR.glob("*.json"))
    if not files:
        print(f"error: no baselines in {BASELINES_DIR}", file=sys.stderr)
        return 2

    results: list[dict] = []
    present_files = {f.name for f in files}

    _full_stack_cache = {"lanes": None, "hash": None}
    if args.full:
        _fs_lanes, _fs_hash = _run_full_stack_once()
        # Empty lanes ({}) means full_stack ran but produced zero trades — a
        # severe regression or data outage. Treat it like an unavailable run
        # (skip primary checks rather than mass-DRIFT every lane), but emit a
        # grep-able token so the drift gate alerts instead of passing silently.
        _full_stack_cache["lanes"] = _fs_lanes or None
        _full_stack_cache["hash"] = _fs_hash
        if not _fs_lanes:
            print("[WARN] FULL_STACK_UNAVAILABLE: full_stack produced no per-lane "
                  "data (crash, timeout, or zero trades) — primary-anchor checks "
                  "skipped; investigate.", file=sys.stderr)

    for f in files:
        if f.name == "EXPECTED_LANES.json":
            continue
        try:
            b = _load(f)
        except json.JSONDecodeError as exc:
            results.append({
                "source": f.name, "lane": "?", "pool": "?",
                "verdict": "?", "weight": None,
                "status": "BROKEN", "reason": f"bad JSON: {exc}",
                "issues": [str(exc)],
            })
            continue
        if args.lane and b.get("lane") != args.lane:
            continue
        row = _audit(b, f)
        if args.full and row["status"] != "BROKEN":
            rstatus, rdetail = _runtime_status(
                b, full_stack_map=_full_stack_cache["lanes"],
                emitted_data_hash=_full_stack_cache["hash"])
            row["repro_status"] = rstatus
            row["repro_msg"] = rdetail
            # Propagate runtime drift to the row status (so --strict catches it),
            # but don't mask a known-broken metadata verdict (STALE/EXPIRED/etc.) —
            # those are the stronger, already-failing signal.
            if rstatus == "DRIFT_DETECTED" and row["status"] not in {
                    "BROKEN", "STALE", "EXPIRED", "MISSING"}:
                row["status"] = "DRIFT_DETECTED"
                row["reason"] = f"runtime drift: {rdetail[:100]}"
        results.append(row)

    # Registry cross-check (skipped under --lane filter to avoid noise)
    if not args.lane:
        registry = _load_registry()
        if registry is None:
            results.append({
                "source": "EXPECTED_LANES.json",
                "lane": "—", "pool": "—",
                "verdict": "—", "weight": None,
                "status": "WARN",
                "reason": "registry missing or malformed",
                "issues": [],
            })
        else:
            results.extend(_audit_registry(registry, present_files))

    if args.json:
        print(json.dumps(results, indent=2, default=str))
        statuses = {r["status"] for r in results}
        bad = statuses & (STRICT_FAIL_STATUSES if args.strict else {"BROKEN", "EXPIRED", "MISSING"})
        return 0 if not bad else 1

    print(f"{'STATUS':6s}  {'LANE':22s}  {'POOL':22s}  {'VERDICT':18s}  {'W':>5s}  REASON")
    print("-" * 110)

    fail_strict = 0
    fail_metadata = 0
    for r in results:
        icon = STATUS_ICONS.get(r["status"], r["status"])
        w = "—" if r["weight"] is None else f"{r['weight']:.2f}"
        print(f"{icon:6s}  {r['lane'][:22]:22s}  {r['pool'][:22]:22s}  {r['verdict'][:18]:18s}  {w:>5s}  {r['reason']}")
        if r["status"] in {"BROKEN", "EXPIRED", "MISSING"}:
            fail_metadata += 1
        if r["status"] in STRICT_FAIL_STATUSES:
            fail_strict += 1
        if args.full and r.get("repro_status"):
            print(f"        repro: {r['repro_status']}  {r['repro_msg'][:80]}")

    print()
    counts = {s: sum(1 for r in results if r["status"] == s) for s in STATUS_ICONS}
    summary_parts = [f"{n} {s}" for s, n in counts.items() if n]
    print(f"{len(results)} entries audited; " + "; ".join(summary_parts))
    if args.strict:
        return 0 if fail_strict == 0 else 1
    return 0 if fail_metadata == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
