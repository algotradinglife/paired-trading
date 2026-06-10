---
name: feedback-multi-tf-sweet-spot-timing-pitfall
description: 2026-05-25 尝试给 analyze_sweet_spots_pool.py 加 --topology multi-TF context，codex 8 轮抓出 4 个独立 leakage，最终 revert 改作 future work
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 3c6bc7f2-4594-4d16-89a0-0cb59a248533
---

**规则**：往 sweet-spot finder（或任何 OOS 分析脚本）加 multi-TF context (higher_relation / lower_relation) 之前，**必须**先把 bar-timestamp 语义对齐做好。每种 instrument class 的 session 收盘时间不同（美股 16:00 ET, CN 期货分时段），且 snapshot 文件的 bar timestamp 约定（start-of-bar vs end-of-bar）也不同。

**Why**（2026-05-25 实战）：尝试给 `scripts/analyze_sweet_spots_pool.py` 加 `--topology A|B` 让 sweet-spot 桶包含 `higher_relation` / `lower_relation` 维度。8 轮 `codex review --uncommitted` 连续抓出独立 leakage：

1. **NaN-relation 行被错误聚合**：`--topology` 启用时，foreign-TF 覆盖外的 signals 仍进入 NaN bucket，被当成"sweet spot"
2. **空 summary merge KeyError**：MTF 过滤后 train_sub / test_sub 可能为空，summarize 返回零列 df, merge 炸
3. **bar_delta 用首差不稳**：`bars["timestamp"].iloc[1] - iloc[0]` 在第一对 bars 跨周末/假日时偏大数日
4. **weekly bar start-of-week 包含未来 Fri 数据**：仅 `<= signal_t` slice 不够，需要 `foreign_start + foreign_duration < signal_t`
5. **签名超过 foreign 覆盖期取末值**：enrich_with_* 在 signal_t > last_foreign_end 时仍返回最后已知 state，污染近期 signals
6. **lower enricher 的 intraday_grace_minutes 默认 30min**：shift 到 bar-close 后这个 grace 反而 re-introduce 前向泄漏
7. **mtf_n status count 漏算只下不上**：单 lower 覆盖时打印 "0 with multi-TF context" 误导
8. **US `_15`/`_60` 含 after-hours bars**：用 full median daily interval shift 仍会让 enrich 吃到收盘后的 intraday

**最终 revert**：把 `--topology` 扩展撤掉，让 sweet-spot finder 保留干净的 single-TF 模式。多 TF 集成留 future work，前提是先解决：
- 每 instrument_class 的 session 收盘时刻表（用作 signal_t 的真实"已知时刻"）
- foreign-TF bar 的 timestamp 语义是否 start/end，需要文档化
- 严格的 "foreign bar 已完整 close" 判定（不只是 `<= signal_t`）

**How to apply**：
- 如果未来必须做 multi-TF sweet-spot，先实现 `engine/timing/session.py` 之类的 session-aware lookup 层，再让任何分析脚本调用
- 或者绕开：用 fetch_polygon 时把 daily bar timestamp 改成 end-of-session（破坏 backward-compat，需要 schema 讨论）
- engine 内部 `enrich_with_higher_tf` / `enrich_with_lower_tf` 已被 [[project-validated-bottom-setup]] 和 [[project-cn-policy-oos-validated]] 在 backtest 里大量使用 —— **可能也有同样的 timing leak**，policy weight 校准可能因此略偏。这是 [[project-us-policy-oos-fragile-rules]] 验证 B1/F3 sample 太薄之外的**第二个**潜在校准误差源，下次 refit 应该考虑这个角度
- session goal "持续寻找高胜率甜区" 现在主路径是单 TF + Z1+Z2+Z3 context_features，已通过 OOS 验证产出 `US-bot-swing-mid` (参见 [[project-initial-sweet-spots-2026-05-25]])
- 8 轮 codex review 是上限信号：如果某个 feature 4 轮后还在抓新 bug，认真考虑 revert + 留 future work，不要硬冲（这就是这次的教训）
