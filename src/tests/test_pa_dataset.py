"""验收测试 — PA 标注数据集 P0（kanban t_6cf9f9c4）。

覆盖规范 §7.1（可复现/与参考一致）+ §7.2（无前视）。需 5min store + philosopher loader。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC))
TP_SRC = Path.home() / "workspace/quant/strats/trade-philosopher/src"
if TP_SRC.exists():
    sys.path.insert(0, str(TP_SRC))

pytestmark = pytest.mark.skipif(
    not TP_SRC.exists(), reason="trade-philosopher loader 不可用（跨仓数据依赖）"
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
