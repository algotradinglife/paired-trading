"""Audit `baselines/*.json` baseline artifacts.

Two modes:
  default (metadata)  — fast scan: expiry / verdict / staleness / schema
  --full              — also re-execute each baseline's `repro_command`
                        (slow; opt-in only)

A baseline file is the single source of truth for "what evidence backs this
lane × pool's policy_weight". Detector docstrings should REF the JSON, not
inline numbers.

Usage:
    python scripts/validate_baselines.py
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

REQUIRED_FIELDS = (
    "schema_version", "lane", "pool", "verdict",
    "policy_weight_assigned", "valid_until", "commit_hash",
    "data_snapshot", "last_verified",
)

VERDICTS = {
    "STRONG PASS", "PASS", "CONDITIONAL PASS",
    "marginal", "REJECT", "STALE", "DRIFT",
}

STATUS_ICONS = {
    "OK":      "[ OK ]",
    "WARN":    "[WARN]",
    "EXPIRED": "[XPRD]",
    "STALE":   "[STAL]",
    "DRIFT":   "[DRFT]",
    "BROKEN":  "[BRKN]",
}


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
    # sample integrity
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
    """Return (status, reason)."""
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


def _audit(b: dict, source: pathlib.Path) -> dict:
    issues = _check_schema(b)
    status, reason = _check_freshness(b)

    verdict = b.get("verdict", "UNKNOWN")
    weight = b.get("policy_weight_assigned", None)
    lane = b.get("lane", "?")
    pool = b.get("pool", "?")

    # Verdict-specific overrides
    if verdict == "STALE":
        status = "STALE"
        reason = "verdict=STALE (known broken)"
    elif verdict == "DRIFT":
        status = "DRIFT"
        recommended = b.get("policy_weight_recommended")
        reason = f"verdict=DRIFT; weight={weight} but recommended={recommended}" if recommended else "verdict=DRIFT (needs re-validation)"
    elif issues:
        status = "BROKEN"
        reason = f"schema: {issues[0]}"

    # Sanity: STALE/REJECT should not assign a non-zero live weight
    if verdict in {"STALE", "REJECT"} and (weight or 0) > 0:
        status = "BROKEN"
        reason = f"verdict={verdict} but policy_weight={weight} (>0)"

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
    """Execute the JSON's `repro_command` and capture stdout tail."""
    import shlex
    import subprocess

    cmd = b.get("repro_command", "")
    if not cmd:
        return "WARN", "no repro_command"
    # Strip leading `cd src && ` if present
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
    return "OK", f"repro succeeded; tail:\n{tail}"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--lane", help="only audit baselines whose lane matches")
    p.add_argument("--full", action="store_true",
                   help="also execute each repro_command (slow)")
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

    results = []
    for f in files:
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

    if args.json:
        print(json.dumps(results, indent=2, default=str))
        return 0 if all(r["status"] in {"OK", "WARN"} for r in results) else 1

    # Table output
    print(f"{'STATUS':6s}  {'LANE':22s}  {'POOL':22s}  {'VERDICT':18s}  {'W':>5s}  REASON")
    print("-" * 110)
    fail = 0
    for r in results:
        icon = STATUS_ICONS.get(r["status"], r["status"])
        w = "—" if r["weight"] is None else f"{r['weight']:.2f}"
        print(f"{icon:6s}  {r['lane'][:22]:22s}  {r['pool'][:22]:22s}  {r['verdict'][:18]:18s}  {w:>5s}  {r['reason']}")
        if r["status"] in {"BROKEN", "EXPIRED"}:
            fail += 1
        if args.full and r.get("repro_status"):
            print(f"        repro: {r['repro_status']}  {r['repro_msg'][:80]}")

    print()
    summary = (f"{len(results)} baselines audited; "
               f"{fail} BROKEN/EXPIRED; "
               f"{sum(1 for r in results if r['status']=='STALE')} STALE; "
               f"{sum(1 for r in results if r['status']=='WARN')} WARN.")
    print(summary)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
