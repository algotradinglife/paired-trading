# 全 pool smoke baseline — 2026-06-08

post-F1 + POC + 8-lane structural stops（commit `d4b933d0` 起点）。
对 4 个 pool × 2 个 window 做 smoke 验证，建立"今天的产线状态"
baseline。

## Per-pool 信号计数

| Pool | Window | 记录数 | Level 分布 | invalidation_level 填充率 | DIR attached |
|------|--------|--------|-----------|---------------------------|--------------|
| US | 7d | 4 | pa_us_60min:1, context_a:1, pa_us_dif_pos:2 | 4/4 | 3/4 |
| US | 30d | 10 | pa_us_60min:3, context_a:5, pa_us_dif_pos:2 | 10/10 | 5/10 |
| CN_METAL | 7d | 1 | pa_h2:1 | 1/1 | 1/1 |
| CN_METAL | 30d | 7 | bpull:2, pa_h2:3, vflush:1, context_a:1 | 7/7 | 3/7 |
| CN_BOND | 7d | 0 | — | — | — |
| CN_BOND | 30d | 0 | — | — | — |
| CN_COMMODITY | 7d | 0 | — | — | — |
| CN_COMMODITY | 30d | 2 | pa_h2_climax:2 | 2/2 | 0/2 |

合计：24 emit 记录，**24/24 (100%) 都有 invalidation_level** —— 8/8 lane 全部结构止损的工程目标达成。

## DIR module 工作状态

| 路径 | 触发 lane | 12 个 DIR-attached 记录覆盖 |
|------|----------|---------------------------|
| 10-source（含 signal_tf_60min + resonance） | pa_us_60min | 4 |
| 8-source（baseline） | pa_us_dif_pos, pa_h2, pa_cn_bond | 8 |

**Verdict 分布**：12/12 = **skip**（无一过 threshold）

**Resonance 分布**：4/4 = **n/a**（60min 路径上 daily_structure 始终 neutral——TR_FORMING 中段位置——所以 resonance 触发不了）

## 关键观察

1. **结构止损全填**：所有 lane 在所有 pool 上都正确填出 invalidation_level，0 个例外。证明 8/8 lane 工程化完成
2. **POC 数据贫瘠**：4 个 pa_us_60min 记录里没有任何一个出现 resonance=YES——daily 结构在这段时间一直 neutral。要 N 大才能看到 resonance 起作用
3. **CN_BOND 7d/30d 都 0 信号**：3 个 symbol 池本身就稀，30 天 0 emit 不算异常。需要更长窗口或者更多池
4. **CN_COMMODITY 30d 出 2 个 pa_h2_climax**：dce_m 和 czce_ma 都是 _CN_AGRI_POS_SYMBOLS 池里的，符合预期
5. **US sweet-spot 命中率 100%**：3/3 pa_us_60min 记录都匹配了 `US-PA-60min-uptrend-hopp`（B1-2 添加的 PA-native rule）。说明 PA-native sweet spots 配置正确
6. **score_today 输出对所有池都正常 serialise**：JSON 都正确写出，没有 schema 错误

## 待积累的指标

| 指标 | 当前样本 | 需要 | 用途 |
|------|---------|------|------|
| pa_us_60min DIR 通过率 | 0/4 (skip) | n=50+ | 决定 10-source threshold 是否要调成绝对 0.50 |
| resonance=YES 比例 | 0/4 | n=20+ | 验证 POC 架构的真实信号 |
| 60min lane structural stop max-adverse-excursion | 30 历史样本（B1-4 时） | n=100+ | 校准 0.5% buffer |
| 不同 lane 的 verdict 一致性 | 4 lane × 数据点 | 长期 | 判断 DIR 该 promote 谁 gate-only |

## 复现命令

```bash
cd src
for pool in US CN_METAL CN_BOND CN_COMMODITY; do
  for win in 7 30; do
    DERIVED_ROOT="/Volumes/Data Drive/derived" \
      .venv/bin/python scripts/score_today.py \
      --pool $pool --window-days $win \
      --quant-data-root data/quant \
      -o /tmp/smoke_${pool}_${win}.json
  done
done
```

## 后续推荐

依次：
1. **每周跑一次此 smoke**，把数字累积到 `doc/repro/full_pool_smoke_<date>.md` 时序里
2. **n=50+ 后回头看 DIR threshold**——目前 12/12 skip 不够下结论
3. **CN_BOND 信号补充**：要么扩池（加更多债期），要么接受当前低 signal density
