# 期权归因 — 市场数据重跑（P0 修复，2026-06-12）

接替 `options_attribution_2026-06-10.md`（slice-1，MODEL_DOMINATED）。
期权日线回填到 2024-07 后的市场覆盖期重跑。

## 结果（净 20bps 往返成本，次日收盘入场）

| | modeled_fraction | reliability | verdict | IS net | OOS net |
|---|---|---|---|---|---|
| **ag** | **0.31**（slice-1: 0.951）| **MARKET_BACKED** | **REGIME_ONLY** | 0.864 (n=9) | 1.324 (n=20) |
| **au** | **0.222**（slice-1: 0.788）| **MARKET_BACKED** | **PROMOTE** | 1.715 (n=8) | 1.376 (n=19) |

**P0 目标（<0.3）达成。** 关键解读：

- **au 的 PROMOTE 第一次有市场数据背书**（slice-1 的 PROMOTE 随 IV 假设摆动；
  现在 78% 交易按真实挂牌合约市场价结算，IV 假设只剩 22% 残余敞口）。
- **ag 从 PROMOTE 降为 REGIME_ONLY**：市场价下 IS 折（2024H2，n=9）净值 0.864
  不过线。这是真实信息 —— slice-1 的 ag PROMOTE 是 Black-76 + 钉死 IV 0.13
  画出来的。OOS 折（2025-2026，n=20）1.324 仍为正。
- **薄折警告**：IS n=8/9。verdict 视为暂定，随市场历史累积复验。

## 与 slice-1 不可直接对比的三处语义变化

1. 入场：信号日收盘 → 次日收盘（消前视），无次日 bar 的交易剔除
2. 成本：0 → 20bps 往返（10 佣金 + 10 滑点），毛/净双轨报告
3. 窗口：全历史 → `--since 2024-07-01`（市场覆盖期），IS/OOS 切点 2024

## 方法核心：挂牌合约对齐（`_snap_to_listed`）

selector 按 DTE 算术 + %OTM 取整生成**理论**合约，三处与现实脱节，
造成市场覆盖期内仍大量模型回退（修复前 ag modeled 0.69 / au 0.85）。另有 codex P1 修正：晚于信号上市的合约不算可交易（首根 bar ≤ 信号日才候选，到期代理同样只看信号时已上市的合约）：

| 脱节 | 现实 | 处理 |
|------|------|------|
| 月份 | au 期权只挂双月；ag 部分月份不挂 | 在挂牌月中选 |
| 期权到期 | 比期货月早约一个月（au2502 期权 1 月下旬停牌）| 用链最后 bar 日做期权到期代理，DTE 窗口 (20,75) 建立在其上 |
| 行权价/上市时点 | 理论 strike 未必挂牌；合约可能晚于信号上市 | coverage 感知（信号日起 ≥5 根才候选），最近 OTM 行权价 |

snap 占比：ag 11/29、au 17/27（大部分交易需要对齐 —— **live selector 的
同款缺陷待修**，见后续项）。snap 失败（窗口内无覆盖链）回退理论合约 +
Black-76，计入 modeled_fraction。

## 复现

```bash
uv run python scripts/backtest_options_attribution.py --underlying ag \
  --since 2024-07-01 --is-cutoff-year 2024
uv run python scripts/backtest_options_attribution.py --underlying au \
  --since 2024-07-01 --is-cutoff-year 2024
```

baseline：`baselines/options_{ag,au}.json`（slice-1 值保存在 history）。

## 后续项

1. **live selector 挂牌对齐**：score_today 的期权建议沿用理论合约
   （price/IV 部分 n/a 的根因之一）——把 `_snap_to_listed` 思路移植到
   `cn_{ag,au}_selector`（或新 `BaseOTMSelector`，design doc P3 一并做）。
2. **薄折复验**：市场历史每累积一个季度复跑一次；IS 折样本 >20 后
   verdict 转正式。
3. ag REGIME_ONLY 的含义评估：是否把 ag call 建议降级为 monitoring
   （现 score_today 仍对 ag 信号给期权建议）—— 用户决策项。
4. put 侧归因 harness（put 链数据已就位）— Phase C 主线。

## 更新（2026-06-12b）：生产合约规则落地后的最终数字

用户锁定规则「期权到期日 ≥2 周选本月，否则选次月」+ 挂牌行权价对齐
已实装进生产 selector（`engine/options/expiry_select.py`，死链用链终止日
做精确到期、活链用近似；au 理论回退遵守双月挂牌周期）。归因经 emission
replay 自动继承生产规则，**snapped_n=0**（harness 直接测量生产行为）：

| | frac | verdict | IS net | OOS net |
|---|---|---|---|---|
| ag | 0.241 | **PROMOTE** | 1.384 (n=9) | 1.281 (n=20) |
| au | 0.222 | **PROMOTE** | 1.521 (n=8) | 1.369 (n=19) |

ag 此前的 REGIME_ONLY（IS 0.864）是 (20,75) 窗口近似选出的远月合约；
生产规则选更近月（权利金更便宜、gamma 更快），IS 折转正 —— **合约选择
规则本身是 edge 的组成部分**。薄折警告维持（IS n=8/9，暂定）。

live 验证：score_today 期权建议现带 store 实价 price/IV（`[store]` 源标记）。
