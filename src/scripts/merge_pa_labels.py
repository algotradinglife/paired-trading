"""P1 — 合并复刻决策标到 PA 数据集（按 id JOIN，可重入）。kanban t_6cf9f9c4

字段归属（researcher 在 t_3d25c2f5 拍板）：
  data-engineer（本脚本，确定性脊柱）：features_det / liquidity / split / outcome / context_ref /
    candidate_source / dedup_key —— 全部取自 P0 数据集（pa_dataset_{product}.jsonl）。
  philosopher（复刻语料）：decision / decision_trace / diagnosis_summary / label_source。

关键：复刻语料内嵌 outcome 被换月跳变虚增（gross_r 可 > payoff，researcher 已验证），**丢弃**，
outcome 一律用 P0 确定性 simulate_order 口径。

可重入：philosopher 因配额分批续跑，语料是增量的——已 label 的 id JOIN 进来填 decision；
未 label 的保持 decision=null / label_source=pending_replica。重跑安全（幂等）。

用法：
  cd src && python3 scripts/merge_pa_labels.py \
      --base data/review/pa_dataset_rb.jsonl \
      --labels ~/workspace/quant/strats/trade-philosopher/runs/_replica/pa_dataset_rb_claude.jsonl \
      --out data/review/pa_dataset_rb.labeled.jsonl
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# 仅从复刻语料取这些 decision 侧字段，其余一律用 P0 脊柱（含 outcome）
REPLICA_FIELDS = ("decision", "decision_trace", "diagnosis_summary")


def _read_jsonl(fp: Path) -> list[dict]:
    return [json.loads(ln) for ln in open(fp) if ln.strip()]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", type=Path, required=True,
                    help="P0 确定性数据集 pa_dataset_{product}.jsonl")
    ap.add_argument("--labels", type=Path, required=True,
                    help="philosopher 复刻语料 jsonl（含 id + decision/decision_trace）")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--label-source", default="replica_claude")
    args = ap.parse_args()

    base = _read_jsonl(args.base)
    labels = _read_jsonl(args.labels)
    lab_by_id: dict[str, dict] = {}
    for r in labels:
        rid = r.get("id")
        if rid and r.get("decision") is not None:   # 只接已实标的；占位/未标跳过
            lab_by_id[rid] = r

    base_ids = {r["id"] for r in base}
    n_filled = 0
    for r in base:
        lab = lab_by_id.get(r["id"])
        if lab is None:
            r["label_source"] = r.get("label_source") or "pending_replica"
            continue
        for f in REPLICA_FIELDS:
            r[f] = lab.get(f)
        r["label_source"] = args.label_source
        # outcome / features_det / liquidity / split 保持 P0 脊柱不动（确定性口径）
        n_filled += 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        for r in base:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")

    orphans = sorted(set(lab_by_id) - base_ids)   # 语料里有、脊柱里无的 label（口径差/被去重）
    summary = {
        "phase": "P1-merge", "base": str(args.base), "labels": str(args.labels),
        "n_base": len(base), "n_labels_available": len(lab_by_id),
        "n_filled": n_filled, "n_pending": len(base) - n_filled,
        "n_label_orphans": len(orphans), "orphan_ids_sample": orphans[:10],
        "note": "outcome/features_det/liquidity/split 取自 P0 脊柱；decision/trace/diagnosis 取自复刻语料；语料内嵌 outcome 已丢弃（换月虚增）",
    }
    with open(args.out.with_suffix(".summary.json"), "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
