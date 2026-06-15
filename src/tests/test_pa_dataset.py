"""验收测试 — PA 标注数据集 P0（kanban t_6cf9f9c4）。

覆盖规范 §7.1（可复现/与参考一致）+ §7.2（无前视）。需 5min store + philosopher loader。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC))
# Robust sibling-repo resolution (NOT Path.home() — fails under Hermes worker profiles
# where HOME differs, silently skipping these tests; reviewer card t_a0af6bc4).
from scripts.eval_spec001_ev import _DEFAULT_TP_SRC as TP_SRC  # noqa: E402
if TP_SRC.exists():
    sys.path.insert(0, str(TP_SRC))

pytestmark = pytest.mark.skipif(
    not (TP_SRC / "tp" / "pa" / "cn_data.py").exists(),
    reason="trade-philosopher loader 不可用（跨仓数据依赖）"
)


def _first_signal_bars():
    from scripts.backtest_spec001_proxy import detect_signals
    try:
        from tp.pa.cn_data import load_cn_window
        bars = load_cn_window("rb2101", "5min", 200000)
    except Exception as e:  # loader present but 5min store absent/unreadable (codex P2)
        pytest.skip(f"5min data store unavailable: {e}")
    if not bars:
        pytest.skip("5min store empty for rb2101")
    sigs = detect_signals(bars)
    return bars, sigs


def test_features_det_no_lookahead():
    """features_det 截断未来 bar 后必须不变（无前视）。"""
    import scripts.build_pa_dataset as B
    from scripts.backtest_spec001_proxy import _atr
    bars, sigs = _first_signal_bars()
    assert sigs, "rb2101 应有候选"
    s = sigs[0]
    i = s["i"]
    full = B._features_det(bars, i, s, _atr(bars))
    trunc = bars[: i + 1]
    cut = B._features_det(trunc, i, s, _atr(trunc))
    assert full == cut, "features_det 含前视泄漏"


def test_outcome_matches_reference_artifact():
    """结果标引擎须与 researcher 参考工件 spec001_proxy_ev.json 一致（§7.1）：同一 ts → 同一
    gross_r（证明复用了同一 simulate_order 引擎）。两条管道按 (product,day) 去重的 tie-break
    可不同（builder 在去重前先剔 unresolved，proxy 不剔），故按**交集**逐单核对、并要求高重叠。"""
    import json
    ref_fp = SRC / "data/review/spec001_proxy_ev.json"
    ds_fp = SRC / "data/review/pa_dataset_rb.jsonl"
    if not (ref_fp.exists() and ds_fp.exists()):
        pytest.skip("参考工件或数据集未生成")
    ref = json.load(open(ref_fp))
    ref_map = {o["ts"]: round(o["gross_r"], 6)
               for o in ref["orders"]
               if o["product"] == "rb" and o.get("triggered") and o.get("resolved")}
    mine = [json.loads(ln) for ln in open(ds_fp)]
    mine_map = {r["ts_utc"]: round(r["outcome"]["gross_r"], 6)
                for r in mine
                if r["outcome"]["triggered"] and r["outcome"]["resolved"]}
    common = set(ref_map) & set(mine_map)
    assert len(common) >= 0.95 * min(len(ref_map), len(mine_map)), "与参考工件重叠过低"
    mism = [t for t in common if ref_map[t] != mine_map[t]]
    assert not mism, f"{len(mism)} 条 gross_r 与参考不一致"


def test_split_and_dedup_discipline():
    """时间切分单调 + (product,day) 唯一（§7.2）。"""
    import json
    ds_fp = SRC / "data/review/pa_dataset_rb.jsonl"
    if not ds_fp.exists():
        pytest.skip("数据集未生成")
    recs = [json.loads(ln) for ln in open(ds_fp)]
    keys = [tuple(r["dedup_key"]) for r in recs]
    assert len(keys) == len(set(keys)), "(product,day) 去重失败"
    # 同一 split 内的日期不应晚于后续 split 的最早日期（时间切分单调）
    by = {}
    for r in recs:
        by.setdefault(r["split"], []).append(r["ts_utc"][:10])
    if "train" in by and "test" in by:
        assert max(by["train"]) <= min(by["test"]), "train/test 时间重叠"


def test_merge_keeps_deterministic_outcome_and_attaches_decision():
    """P1 合并：outcome 必须取 P0 脊柱（确定性），decision/trace 取复刻语料（§字段归属）。"""
    import json
    base_fp = SRC / "data/review/pa_dataset_rb.jsonl"
    merged_fp = SRC / "data/review/pa_dataset_rb.labeled.jsonl"
    if not (base_fp.exists() and merged_fp.exists()):
        pytest.skip("数据集或合并产物未生成")
    base = {json.loads(ln)["id"]: json.loads(ln) for ln in open(base_fp)}
    merged = [json.loads(ln) for ln in open(merged_fp)]
    assert len(merged) == len(base), "合并不应增删脊柱记录"
    for r in merged:
        # outcome 永远等于 P0 脊柱（决策侧不得覆盖确定性 outcome）
        assert r["outcome"] == base[r["id"]]["outcome"], f"{r['id']} outcome 被污染"
        if r["label_source"] == "replica_claude":
            assert r["decision"] is not None and r["decision_trace"], "已标记录须有 decision+trace"
        else:
            assert r["label_source"] == "pending_replica"


def test_p2_adjudication_queue_integrity():
    """P2 队列：id ⊆ labeled、分歧类型与确定性 outcome 自洽（§7.6）。"""
    import json
    lab_fp = SRC / "data/review/pa_dataset_rb.labeled.jsonl"
    q_fp = SRC / "data/review/pa_adjudication_queue_rb.jsonl"
    if not (lab_fp.exists() and q_fp.exists()):
        pytest.skip("队列或合并产物未生成")
    lab = {json.loads(ln)["id"]: json.loads(ln) for ln in open(lab_fp)}
    queue = [json.loads(ln) for ln in open(q_fp)]
    for q in queue:
        assert q["id"] in lab, "队列 id 必须来自 labeled"
        dt_, basis, oc = q["divergence_type"], q["outcome_basis"], q.get("outcome") or {}
        if dt_ == "declined_but_would_target":
            # 复刻没下单：用 proxy 候选反事实（合理，保留）
            assert q["replica_order"] is False and basis == "proxy_candidate"
            assert oc.get("exit_kind") == "target"
        elif dt_ == "decided_order_but_stopped":
            # 复刻下单：必须用复刻订单自身 simulate_order outcome（codex P1 修复，非 proxy）
            assert q["replica_order"] is True and basis == "replica_order"
            assert oc.get("exit_kind") == "stop"
        elif dt_ == "ordered_unsupported_replica_sim":
            # 限价单等 simulate_order 不支持，显式标记
            assert q["replica_order"] is True and basis == "unsupported_order_type"
        else:
            assert False, f"未知 divergence_type {dt_}"
        assert q["adjudication"] is None  # 真人裁决前为空


def test_p2_triage_routes_human_to_zero():
    """P2 triage：每条有合法 adjudication_route，人工桶 ~0（t_4ed1f529②）。"""
    import json
    q_fp = SRC / "data/review/pa_adjudication_queue_rb.jsonl"
    if not q_fp.exists():
        pytest.skip("队列未生成")
    queue = [json.loads(ln) for ln in open(q_fp)]
    valid = {"auto_resolved", "llm_judge", "human"}
    for q in queue:
        assert q["adjudication_route"] in valid, f"非法 route {q['adjudication_route']}"
        # ordered_stopped 必 auto_resolved；declined>5R 必 auto_resolved
        if q["divergence_type"] == "decided_order_but_stopped":
            assert q["adjudication_route"] == "auto_resolved"
        if (q["divergence_type"] == "declined_but_would_target"
                and (q["outcome"].get("gross_r") or 0) > 5.0):
            assert q["adjudication_route"] == "auto_resolved"
    n_human = sum(1 for q in queue if q["adjudication_route"] == "human")
    assert n_human == 0, f"human 桶应为 0（triage 兜底不应触发），实际 {n_human}"


def test_apply_adjudication_fills_auto_and_llmjudge():
    """P2b 全裁合并（apply_pa_adjudication）：auto_resolved 自动填裁；llm_judge 按 verdict 填；
    无 verdict 的 llm_judge 留 null（pending）；escalate_human 透传。纯数据变换（合成样例）。"""
    from scripts.apply_pa_adjudication import apply_adjudications
    queue = [
        {"id": "rb-auto", "adjudication_route": "auto_resolved",
         "route_reason": "expected_variance", "adjudication": None},
        {"id": "rb-conf", "adjudication_route": "llm_judge",
         "route_reason": "realistic_decline", "adjudication": None},
        {"id": "rb-over", "adjudication_route": "llm_judge",
         "route_reason": "realistic_decline", "adjudication": None},
        {"id": "cu-nojudge", "adjudication_route": "llm_judge",
         "route_reason": "realistic_decline", "adjudication": None},
    ]
    verdicts = [
        {"id": "rb-conf", "verdict": "confirm_replica", "confidence": 0.85,
         "override_action": None, "reason": "忠实", "escalate_human": False,
         "label_source": "llm_judge"},
        {"id": "rb-over", "verdict": "override", "confidence": 0.58,
         "override_action": "偏多挂 buy-stop", "reason": "应小仓做多",
         "escalate_human": True, "label_source": "llm_judge"},
    ]
    out, summary = apply_adjudications(queue, verdicts)
    by_id = {r["id"]: r for r in out}
    # auto_resolved: 确定性自动裁定，method=auto_resolved，verdict 由 route_reason 派生
    a = by_id["rb-auto"]["adjudication"]
    assert a is not None and a["method"] == "auto_resolved"
    assert a["route_reason"] == "expected_variance" and a["escalate_human"] is False
    # llm_judge confirm：透传 verdict/confidence/reason
    c = by_id["rb-conf"]["adjudication"]
    assert c["method"] == "llm_judge" and c["verdict"] == "confirm_replica"
    assert c["confidence"] == 0.85 and c["escalate_human"] is False
    # llm_judge override + escalate_human 透传
    o = by_id["rb-over"]["adjudication"]
    assert o["verdict"] == "override" and o["override_action"] == "偏多挂 buy-stop"
    assert o["escalate_human"] is True
    # 无 verdict 的 llm_judge：留 null（pending），不得伪造
    assert by_id["cu-nojudge"]["adjudication"] is None
    # summary 自洽
    assert summary["n_auto_filled"] == 1
    assert summary["n_llmjudge_filled"] == 2
    assert summary["n_pending_llmjudge"] == 1
    assert summary["n_human_unresolved"] == 0
    assert summary["escalate_human_ids"] == ["rb-over"]


def test_apply_adjudication_rejects_verdict_for_nonjudge_route():
    """verdict 只能落在 llm_judge 路由的记录上；若误指向 auto/human/未知 id，应报告为 unmatched。"""
    from scripts.apply_pa_adjudication import apply_adjudications
    queue = [{"id": "rb-auto", "adjudication_route": "auto_resolved",
              "route_reason": "expected_variance", "adjudication": None}]
    verdicts = [{"id": "rb-auto", "verdict": "override", "confidence": 0.9,
                 "override_action": "x", "reason": "y", "escalate_human": False,
                 "label_source": "llm_judge"},
                {"id": "ghost", "verdict": "confirm_replica", "confidence": 0.9,
                 "override_action": None, "reason": "z", "escalate_human": False,
                 "label_source": "llm_judge"}]
    out, summary = apply_adjudications(queue, verdicts)
    by_id = {r["id"]: r for r in out}
    # auto_resolved 记录不得被 verdict 覆盖（route 不符）
    assert by_id["rb-auto"]["adjudication"]["method"] == "auto_resolved"
    assert sorted(summary["unmatched_verdict_ids"]) == ["ghost", "rb-auto"]
    assert summary["n_llmjudge_filled"] == 0


# ---- P3 跨品种组合数据集（rb+cu+au）on-disk 工件验收 ----

def test_combined_dataset_covers_three_products():
    """P3 组合脊柱：含 rb/cu/au，时间切分单调，(product,day) 去重唯一。"""
    import json
    ds = SRC / "data/review/pa_dataset_rbcuau.jsonl"
    if not ds.exists():
        pytest.skip("组合数据集未生成")
    recs = [json.loads(ln) for ln in open(ds)]
    insts = {r["instrument"] for r in recs}
    assert {"rb", "cu", "au"} <= insts, f"缺品种 {insts}"
    keys = [tuple(r["dedup_key"]) for r in recs]
    assert len(keys) == len(set(keys)), "(product,day) 去重失败"
    by = {}
    for r in recs:
        by.setdefault(r["split"], []).append(r["ts_utc"][:10])
    if "train" in by and "test" in by:
        assert max(by["train"]) <= min(by["test"]), "train/test 时间重叠"


def test_combined_merge_conserves_outcome():
    """P3 组合合并：outcome 必须逐条等于 P0 组合脊柱（决策侧不得污染确定性 outcome）。"""
    import json
    base_fp = SRC / "data/review/pa_dataset_rbcuau.jsonl"
    merged_fp = SRC / "data/review/pa_dataset_rbcuau.labeled.jsonl"
    if not (base_fp.exists() and merged_fp.exists()):
        pytest.skip("组合数据集或合并产物未生成")
    base = {json.loads(ln)["id"]: json.loads(ln) for ln in open(base_fp)}
    merged = [json.loads(ln) for ln in open(merged_fp)]
    assert len(merged) == len(base)
    for r in merged:
        assert r["outcome"] == base[r["id"]]["outcome"], f"{r['id']} outcome 被污染"
        if r["label_source"] == "replica_claude":
            assert r["decision"] is not None and r["decision_trace"]


def test_adjudicated_queue_rb_fully_resolved():
    """P2b 全裁队列：每条 auto_resolved 已填 method=auto_resolved；有 verdict 的 llm_judge 已填；
    human 未决=0；escalate_human 记录仍带 adjudication（可选真人复核，非阻塞）。
    cu/au llm_judge 无 verdict 可留 pending（philosopher 增量），但不得伪造。"""
    import json
    q_fp = SRC / "data/review/pa_adjudication_queue_rbcuau.adjudicated.jsonl"
    if not q_fp.exists():
        pytest.skip("全裁队列未生成")
    queue = [json.loads(ln) for ln in open(q_fp)]
    for q in queue:
        route, adj = q["adjudication_route"], q.get("adjudication")
        if route == "auto_resolved":
            assert adj is not None and adj["method"] == "auto_resolved"
        elif route == "llm_judge" and adj is not None:
            assert adj["method"] == "llm_judge" and adj["verdict"] in {"confirm_replica", "override"}
        # pending llm_judge（adj is None）仅允许出现在非 rb（philosopher 尚未对该品种 llm_judge）
        if route == "llm_judge" and adj is None:
            assert not q["id"].startswith("rb"), f"{q['id']} rb llm_judge 不应 pending"
    # 真人未决必须为 0（triage 兜底 human=0；escalate_human 是可选复核而非阻塞）
    n_human_unresolved = sum(1 for q in queue
                             if q["adjudication_route"] == "human" and q.get("adjudication") is None)
    assert n_human_unresolved == 0
    # escalate_human 标记的记录必须已填 adjudication（不能既升级又留空）
    for q in queue:
        adj = q.get("adjudication")
        if adj and adj.get("escalate_human"):
            assert adj.get("verdict") is not None
    # 交付态：rb+cu+au verdict 全到位 → 队列全裁（0 未裁，human 0）
    n_unadj = sum(1 for q in queue if q.get("adjudication") is None)
    assert n_unadj == 0, f"全裁队列应 0 未裁，实际 {n_unadj}"
