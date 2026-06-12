# 迁移后全量重验证 — 2026-06-12

数据回填完成（`check_data_coverage.py`：**0 required 缺失**）后的首次
全量对账。最终 dashboard：**12 OK / 1 STALE（已知冻结）**。

## 核心结论

**CN 侧零 re-anchor 通过。** cu/au/ag 2021-2022 合约月份补齐后，自研
主连合成（`data/continuous.py`，OI/volume 度量 + 双向确认滚月）在原始
5.5 年 baseline 锚的容差内复现全部 CN cell：

| Cell | 锚（旧机 5.5y）| 本次 | 判定 |
|------|------|------|------|
| bpull cn_metal | n=172 +0.179R | 容差内 | OK，未动锚 |
| pa_h2 cn_metal | n=102 +0.189R | 容差内 | OK，未动锚 |
| context_a cn_metal | n=38 级 | 容差内 | OK |
| vflush cu+sc | n=42 +0.404R | 容差内 | OK |
| pa_h2 cn_bond | n=73 +0.123R | 容差内 | OK（本机首验）|

这同时验证了三层：quant-cli 数据 ←→ 主连合成 ←→ BarStore seam 的端到端
等价性。**CN baseline 刻意不 re-anchor** —— "新管线复现旧锚"比"重钉新锚"
是强得多的证据。

## US 侧：3 个 DRIFT 全部归因后 re-anchor（用户批准 2026-06-12）

| Cell | 旧→新锚 | 归因 |
|------|---------|------|
| pa_us_60min | n 146→97, EV +0.086→+0.356 | 人口构成：11 个非核心标的小时线仅 2024-06 起（近期段信号抬高聚合）。核心三标的逐位复现（IWM n=15 +0.633 / QQQ n=11 −0.136）|
| context_a US | n 178→116 | h=opp 门控需 60min bars，8 个标的 2024 前无小时线 |
| pa_h2 US (pa_us_dif_pos) | n 66→47 | 同上 |

三者均注记 **EXPECT ONE MORE DRIFT**：非核心小时线历史回填后会再漂一次，
属预期内（见 `doc/data_gaps_post_sync_2026-06-12.md` 非必需项）。
verdict / policy weight 全部未动。旧锚保存在各 baseline 的
`reanchor_history`。

## data_snapshot_hash 端到端启用

- `_data_hash_for_bars` 修复后（剔除当日在飞 bar）hash 在静止 store 上
  跨运行稳定：`sha256:c204d2e2…`（已钉入 3 个 re-anchor 的 baseline）。
- 自此 drift-gate 的"数据 vs 代码"漂移归因真正可用（NEXT_SESSION
  2026-06-10 的遗留 opt-in 项完成）。

## 过程记录

- 第一次尝试（2026-06-12 早）在第二波回填进行中误启动，re-anchor 后
  发现 store 仍在写入（10 分钟 147 文件），**全部撤销** —— 锚必须钉在
  静止快照上。教训已并入流程：先 `find -mmin -10` 确认静止。
- options_{ag,au} baseline 补 schema + 注册 pending；验证器 VERDICTS
  增加 PROMOTE/REGIME_ONLY。
- pa_h2_climax 维持 STALE 冻结（weight=0，历史证据保全）。

## 后续

- drift-gate cron 即装（迁移收官项）。
- 期权归因重跑（P0）：ag/au 期权历史已达 2024-07 目标 → 可排期。
- 非核心 US 小时线回填到位后：预期 3 个 US cell 再漂一次 → 届时做
  最终 re-anchor，pa_us_60min 池恢复完整。
