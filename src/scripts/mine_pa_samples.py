"""P2（确定性部分）— 高信息样本挖掘 + 分歧采样 → 人工裁决队列。kanban t_6cf9f9c4

规范 §3-P2 / §7.3 / §7.6。本脚本只做**确定性**的样本选取（无需人/LLM）：
  1. 结果挖掘（§7.3 均衡）：用确定性 outcome 标出会触目标 / 会被扫的样本，给天然均衡的正/负池。
  2. 分歧采样（§7.6 高信息尾部）：proxy↔复刻、复刻 decision↔确定性 outcome 的冲突点入队列：
     - decided_order_but_stopped：复刻下单 → 实际被扫（假阳风险）
     - declined_but_would_target：复刻不下单 → 实际本会达标（错过/假阴，信息最高）
  3. 产出人工裁决队列（annotation-by-correction 用——人只对队列改/点赞）。

⚠️ look-ahead（outcome）**只用于挑样本**，不进 features（规范 §4.3）。
人工裁决（真正填 adjudication.human_verdict）需真人 agent——本脚本只产队列，真人步骤另行阻塞。
可重入：随复刻 label 覆盖增长，重跑队列增量扩大。

用法：
  cd src && python3 scripts/mine_pa_samples.py \
      --labeled data/review/pa_dataset_rb.labeled.jsonl \
      --out-queue data/review/pa_adjudication_queue_rb.jsonl
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.eval_spec001_ev import (  # noqa: E402
    _DEFAULT_TP_SRC, _load_cn_window, _utc, simulate_order,
)

SPEC_ORDER_TYPE = "突破单"          # 突破/止损单：simulate_order 进场语义（做多 high>=entry / 做空 low<=entry）
MAX_WAIT = 288
MAX_HOLD = 288
PROXY_ARTIFACT_R = 5.0              # proxy 候选 target=前摆动高，>5R 多为结构性肥尾人为产物——复刻回避正确


def _route(div: str, outcome: dict | None) -> tuple[str, str]:
    """P2 triage（researcher t_4ed1f529 ②）：把人工裁决压到 ~0。
    返回 (adjudication_route ∈ {auto_resolved, llm_judge, human}, route_reason)。"""
    if div == "decided_order_but_stopped":
        # 复刻下单被扫：单笔本就含负样本，属预期方差——不入人工，由 researcher 聚合 regime 检查
        return "auto_resolved", "expected_variance"
    if div == "declined_but_would_target":
        gr = (outcome or {}).get("gross_r") or 0
        if gr > PROXY_ARTIFACT_R:
            # proxy 候选肥尾 target（如 >5R/277R）不现实，复刻回避正确——自动判定
            return "auto_resolved", "proxy_artifact_decline_correct"
        return "llm_judge", "realistic_decline"          # ≤5R 现实回避：待 philosopher 评审
    if div == "ordered_unsupported_replica_sim":
        return "llm_judge", "unsupported_order_type"      # 限价单等：交 LLM 评审
    return "human", "unrouted"                             # 兜底（不应出现）


def _read(fp: Path) -> list[dict]:
    return [json.loads(ln) for ln in open(fp) if ln.strip()]


def _replica_order_outcome(rec: dict, load_cn_window, bars_cache: dict) -> dict:
    """对**复刻订单自身** (direction/entry/stop/target) 跑 simulate_order（codex P1 修复：
    原误用 proxy 候选单 outcome 给复刻订单归类，方向/价位常不同——无意义）。

    仅支持 突破单（simulate_order 是 stop/breakout 进场）；限价单进场机制相反，标 unsupported。
    """
    d = rec.get("decision") or {}
    if d.get("order_type") != SPEC_ORDER_TYPE:
        return {"basis": "unsupported_order_type", "order_type": d.get("order_type")}
    entry, stop, target = d.get("entry"), d.get("stop"), d.get("target")
    if entry is None or stop is None or target is None:
        return {"basis": "unsupported_order_type", "order_type": d.get("order_type"),
                "reason": "missing E/S/T"}
    order = {"order_direction": d.get("direction"), "entry": float(entry),
             "stop": float(stop), "target": float(target)}
    contract = rec["contract"]
    interval = rec.get("interval", "5min")
    cache_key = (contract, interval)     # key by interval too (codex P2: mixed-interval reuse)
    bars = bars_cache.get(cache_key)
    if bars is None:
        bars = load_cn_window(contract, interval, 200000) or []
        bars_cache[cache_key] = bars
    node_end = dt.datetime.fromisoformat(rec["ts_utc"])
    if not bars or _utc(bars[0]["ts_open"]) > node_end:
        return {"basis": "replica_order", "exit_kind": "window_misanchored",
                "triggered": False, "resolved": False}
    sim = simulate_order(order, bars, node_end=node_end, cost_r=0.0,
                         max_wait_bars=MAX_WAIT, max_hold_bars=MAX_HOLD)
    if sim is None:    # 复刻订单前向未触发进场
        return {"basis": "replica_order", "exit_kind": "no_trigger",
                "triggered": False, "resolved": True}
    return {"basis": "replica_order", "exit_kind": sim.get("exit_kind"),
            "gross_r": sim.get("gross_r"), "triggered": sim.get("triggered"),
            "resolved": sim.get("resolved")}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labeled", type=Path, required=True,
                    help="P1 合并产物 pa_dataset_{product}.labeled.jsonl")
    ap.add_argument("--out-queue", type=Path, required=True,
                    help="人工裁决队列 jsonl 输出")
    args = ap.parse_args()

    recs = _read(args.labeled)
    labeled = [r for r in recs if r.get("label_source") == "replica_claude" and r.get("decision")]
    resolved = [r for r in recs if r["outcome"]["triggered"] and r["outcome"]["resolved"]]

    # 1) 结果挖掘：均衡正/负池（确定性 outcome）
    pos = [r["id"] for r in resolved if r["outcome"]["exit_kind"] == "target"]
    neg = [r["id"] for r in resolved if r["outcome"]["exit_kind"] == "stop"]

    # 2) 分歧采样（仅已标——需复刻 decision 才能比对）
    #    ordered 分支：用**复刻订单自身**的 simulate_order outcome 归类（codex P1 修复）。
    #    declined 分支：复刻没下单，用 proxy 候选 outcome 作反事实（合理，保留）。
    load_cn_window = _load_cn_window(_DEFAULT_TP_SRC)
    bars_cache: dict = {}
    queue = []
    n_unsupported = 0
    for r in labeled:
        ordered = bool(r["decision"].get("order"))
        div = priority = basis = outcome = None
        if ordered:
            ro = _replica_order_outcome(r, load_cn_window, bars_cache)
            if ro["basis"] == "unsupported_order_type":
                # 限价单等：simulate_order 进场机制不符，无法自动判定 → 显式标 unsupported 入队待人工
                div, priority, basis = "ordered_unsupported_replica_sim", 3, "unsupported_order_type"
                outcome = {"order_type": ro.get("order_type")}
            elif ro.get("exit_kind") == "stop":
                div, priority, basis = "decided_order_but_stopped", 2, "replica_order"   # 假阳风险
                outcome = {"exit_kind": "stop", "gross_r": ro.get("gross_r")}
            else:
                continue   # 复刻下单且达标/未触发 → 非此类分歧
        else:
            ek = r["outcome"]["exit_kind"]
            if ek != "target":
                continue
            div, priority, basis = "declined_but_would_target", 1, "proxy_candidate"     # 错过/假阴（信息最高）
            outcome = {"exit_kind": ek, "gross_r": r["outcome"].get("gross_r")}
        if div == "ordered_unsupported_replica_sim":
            n_unsupported += 1
        route, route_reason = _route(div, outcome)
        queue.append({
            "id": r["id"], "ts_utc": r["ts_utc"], "contract": r["contract"],
            "divergence_type": div, "priority": priority,
            "adjudication_route": route,     # auto_resolved | llm_judge | human（triage：人工→~0）
            "route_reason": route_reason,
            "replica_order": ordered,
            "replica_order_type": r["decision"].get("order_type"),
            "replica_direction": r["decision"].get("direction"),
            "replica_win_rate_est": r["decision"].get("win_rate_est"),
            "outcome_basis": basis,          # replica_order | proxy_candidate | unsupported_order_type
            "outcome": outcome,              # 按 basis：复刻订单自身/proxy 反事实
            "decision_trace_ref": r["id"],   # 引用，不内联（trace 在 labeled.jsonl）
            "adjudication": None,            # 待真人 correction：confirm | override + verdict
            "label_source": "replica_claude",
        })
    queue.sort(key=lambda q: (q["priority"], q["ts_utc"]))

    args.out_queue.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_queue, "w") as f:
        for q in queue:
            f.write(json.dumps(q, ensure_ascii=False, default=str) + "\n")

    summary = {
        "phase": "P2-deterministic", "labeled": str(args.labeled),
        "n_records": len(recs), "n_labeled": len(labeled), "n_resolved": len(resolved),
        "outcome_mining": {
            "pos_target": len(pos), "neg_stop": len(neg),
            "imbalance": f"1:{round(len(neg)/len(pos),1)}" if pos else None,
            "note": "正=会触目标/负=会被扫；训练用全 233 正 + 等量/加权负即可达均衡（§7.3）",
        },
        "adjudication_queue": {
            "n_total": len(queue),
            "by_type": dict(Counter(q["divergence_type"] for q in queue)),
            "by_outcome_basis": dict(Counter(q["outcome_basis"] for q in queue)),
            "by_route": dict(Counter(q["adjudication_route"] for q in queue)),
            "n_unsupported_order_type": n_unsupported,
            "note": "triage(t_4ed1f529②) 把人工压到~0：auto_resolved(ordered_stopped=预期方差 / declined>5R=proxy肥尾回避正确)、"
                    "llm_judge(现实 declined≤5R + 限价单 待 philosopher 评审)、human(仅 llm_judge 低置信残余，本步=0)。"
                    "ordered 用复刻订单自身 outcome（codex P1）；declined 用 proxy 反事实。",
        },
        "reentrant": "随复刻 label 覆盖增长，重跑队列增量扩大",
    }
    with open(args.out_queue.with_suffix(".summary.json"), "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
