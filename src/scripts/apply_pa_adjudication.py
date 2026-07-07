"""P2b — 把裁决回填进分歧队列，产出「全裁队列」。kanban t_6cf9f9c4

triage（mine_pa_samples._route）把每条分歧打了 adjudication_route：
  - auto_resolved：确定性自动裁定（ordered_stopped=预期方差 / declined>5R=proxy 肥尾回避正确），
    无需人/LLM → 本脚本直接填 adjudication(method=auto_resolved)。
  - llm_judge：交 philosopher LLM 评审 → 本脚本按 verdict 文件回填 adjudication(method=llm_judge)。
    philosopher 分品种/分批交付 verdict（如 pa_adjudication_rb_llmjudge.jsonl）；**可重入**：
    有 verdict 的填，无 verdict 的留 null（pending_llmjudge），勿伪造。
  - human：仅 llm_judge 低置信残余（triage 兜底，通常 0）。escalate_human=True 的 llm_judge 记录
    仍回填 LLM verdict，但额外标 escalate_human 供真人**可选**复核（非阻塞）。

verdict 文件 schema（philosopher）：id / verdict(confirm_replica|override) / confidence /
  override_action / reason / escalate_human / label_source。

用法：
  cd src && python3 scripts/apply_pa_adjudication.py \
      --queue data/review/pa_adjudication_queue_rbcuau.jsonl \
      --verdicts <tp>/runs/_replica/pa_adjudication_rb_llmjudge.jsonl \
      --out data/review/pa_adjudication_queue_rbcuau.adjudicated.jsonl
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def apply_adjudications(queue: list[dict], verdicts: list[dict]) -> tuple[list[dict], dict]:
    """回填 adjudication（纯数据变换，可重入）。返回 (out_queue, summary)。

    - auto_resolved 路由：填 method=auto_resolved，verdict 派生为 confirm_replica（确定性接受复刻行为），
      escalate_human=False。
    - llm_judge 路由 + 有匹配 verdict：透传 verdict/confidence/override_action/reason/escalate_human。
    - llm_judge 路由 + 无 verdict：adjudication 留 None（pending_llmjudge）。
    - verdict 指向非 llm_judge 路由或未知 id：不回填，计入 unmatched_verdict_ids（口径告警）。
    """
    by_id = {r["id"]: r for r in queue}
    v_by_id = {v["id"]: v for v in verdicts}

    n_auto = n_llm = 0
    unmatched: list[str] = []
    for v in verdicts:
        rec = by_id.get(v["id"])
        if rec is None or rec.get("adjudication_route") != "llm_judge":
            unmatched.append(v["id"])

    out: list[dict] = []
    escalate_ids: list[str] = []
    for rec in queue:
        rec = dict(rec)
        route = rec.get("adjudication_route")
        if route == "auto_resolved":
            rec["adjudication"] = {
                "method": "auto_resolved",
                "verdict": "confirm_replica",       # 确定性接受复刻行为（预期方差 / 回避肥尾正确）
                "route_reason": rec.get("route_reason"),
                "escalate_human": False,
            }
            n_auto += 1
        elif route == "llm_judge":
            v = v_by_id.get(rec["id"])
            if v is not None:
                esc = bool(v.get("escalate_human"))
                rec["adjudication"] = {
                    "method": "llm_judge",
                    "verdict": v.get("verdict"),
                    "confidence": v.get("confidence"),
                    "override_action": v.get("override_action"),
                    "reason": v.get("reason"),
                    "escalate_human": esc,
                    "label_source": v.get("label_source", "llm_judge"),
                }
                if esc:
                    escalate_ids.append(rec["id"])
                n_llm += 1
            # 无 verdict：留 adjudication=None（pending_llmjudge）
        # human / 其它：保持 adjudication 原值（通常 None）
        out.append(rec)

    n_pending_llm = sum(1 for r in out
                        if r.get("adjudication_route") == "llm_judge" and r.get("adjudication") is None)
    n_human_unresolved = sum(1 for r in out
                             if r.get("adjudication_route") == "human" and r.get("adjudication") is None)
    summary = {
        "n_queue": len(out),
        "n_auto_filled": n_auto,
        "n_llmjudge_filled": n_llm,
        "n_pending_llmjudge": n_pending_llm,
        "n_human_unresolved": n_human_unresolved,
        "escalate_human_ids": sorted(escalate_ids),
        "unmatched_verdict_ids": unmatched,
        "by_route": dict(Counter(r.get("adjudication_route") for r in out)),
        "n_unadjudicated": sum(1 for r in out if r.get("adjudication") is None),
    }
    return out, summary


def _read(fp: Path) -> list[dict]:
    return [json.loads(ln) for ln in open(fp) if ln.strip()]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--queue", type=Path, required=True, help="mine_pa_samples 产出的分歧队列")
    ap.add_argument("--verdicts", type=Path, nargs="*", default=[],
                    help="philosopher LLM 裁决 jsonl（可多份，分品种/分批）")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    queue = _read(args.queue)
    verdicts: list[dict] = []
    for vp in args.verdicts:
        verdicts.extend(_read(vp))

    out, summary = apply_adjudications(queue, verdicts)
    summary["queue"] = str(args.queue)
    summary["verdicts"] = [str(v) for v in args.verdicts]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    with open(args.out.with_suffix(".summary.json"), "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
