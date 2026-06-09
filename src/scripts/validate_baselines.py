"""Audit `baselines/*.json` baseline artifacts.

Modes (mutually compatible):
  default (metadata)  — fast scan: expiry / verdict / staleness / schema
  --full              — also re-execute each baseline's `repro_command`
                        (slow; opt-in only; currently only checks exit code,
                        TODO: parse structured output and diff against samples)
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
    "OK":      "[ OK ]",
    "WARN":    "[WARN]",
    "EXPIRED": "[XPRD]",
    "STALE":   "[STAL]",
    "DRIFT":   "[DRFT]",
    "PENDING": "[PEND]",
    "BROKEN":  "[BRKN]",
    "MISSING": "[MISS]",
    "ORPHAN":  "[ORPH]",
}

# Status classes treated as failures under --strict
STRICT_FAIL_STATUSES = {"BROKEN", "EXPIRED", "STALE", "DRIFT", "PENDING", "MISSING"}

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


def _run_repro(b: dict) -> tuple[str, str]:
    """Execute repro_command, capture stdout tail. Currently only exit-code check."""
    import shlex
    import subprocess

    cmd = b.get("repro_command", "")
    if not cmd:
        return "WARN", "no repro_command"
    cwd = REPO_ROOT
    if cmd.startswith("cd src && "):
        cwd = REPO_ROOT / "src"
        cmd = cmd[len("cd src && "):]
    try:
        proc = subprocess.run(
            shlex.split(cmd),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "BROKEN", "repro timed out (>5min)"
    except FileNotFoundError as exc:
        return "BROKEN", f"repro not runnable: {exc}"
    if proc.returncode != 0:
        return "BROKEN", f"repro exited {proc.returncode}; stderr tail: {proc.stderr[-200:].strip()}"
    tail = "\n".join(proc.stdout.strip().splitlines()[-8:])
    return "OK", f"repro succeeded (exit-code only — output drift NOT parsed)"


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
                   help="also execute each repro_command (slow)")
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
            repro_status, repro_msg = _run_repro(b)
            row["repro_status"] = repro_status
            row["repro_msg"] = repro_msg
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
