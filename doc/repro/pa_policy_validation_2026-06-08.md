# PA 引擎 policy table 验证 — 2026-06-08

Followup to `pa_baseline_2026-06-08.md`。**封顶**引擎 `pa_detector.py` docstring 里声明的 5 套 instrument-class 权重，并寻找缺漏的 lane。

## 一句话总结

5 套声明里 4 套基本成立，1 套需 sub-pool 验证；额外发现 **CN_BOND** 是个未列入 policy 的强 lane，应加入。

## 验证矩阵

| Engine 声明 | 路径 / Backtest | 重跑结果 | 状态 |
|------------|----------------|---------|------|
| `us_equity` uptrend+h=opp **0.80** (60min) | pa_swing --dataset us_60min | n=56, EV=+0.384R, F1+0.625 F2+0.708 | ✅ 强支持 |
| `us_equity` legs=1 bonus → **0.90** (60min) | pa_swing --dataset us_60min | n=21, EV=+0.595R, hit 62% | ✅ 方向成立, n<50/fold |
| `us_equity` daily DIF>0+h=opp 0.80 (Context A) | pa_us_k3 | n=68, EV=+0.173R, F1-0.20 F2+0.50 F3+0.21 | ⚠️ daily 路径比 60min 弱 |
| `cn_metal_futures` h=opp **0.75** | pa_cn_structural (Parquet) | n=46, EV=+0.524R, F1+0.59 F2+1.05 F3+0.26 | ✅ 成立 |
| `cn_metal_futures` TR phase × h=opp | pa_cn_structural | n=38, EV=+0.666R, F1+1.14 F2+1.25 | ⭐ 新强 cell |
| `cn_futures` h=opp **0.55** monitoring | pa_cn_phasefilter --pool CN_COMMODITY | n=183, EV=+0.044R, F1+0.31 F2-0.12 F3+0.02 | ✅ "monitoring" 正确 (EV≈0) |
| `czce/cn_agri` **0.0** suppressed | 需 sub-pool 拆 | n/a (CN_COMMODITY 聚合 +0.044R) | ⏸ pending |
| **CN_BOND**（无声明） | pa_cn_phasefilter --pool CN_BOND | n=31, EV=**+0.548R**, F1+0.22 F2+1.50 F3+0.50 | ⭐ 应入 policy table |

## 关键发现

### 1. US 60min vs daily 不等价

- 60min `uptrend+h=opp`：EV +0.384R, F1+0.625, F2+0.708
- daily `DIF>0+h=opp`：EV +0.173R, F1-0.20, F2+0.500, F3+0.214

引擎 0.80 weight 是 60min 的 EV，daily 路径只有 ~45% 的强度。**`score_today` 的实际生产路径是 daily，所以这条 weight 在生产路径上证据偏弱**。
建议要么 (a) 区分 us_equity_60min vs us_equity_daily 给不同权重，要么 (b) 在 score_today 端用 60min 而不是 daily。

### 2. US per-symbol 极不均衡（daily）

强（h=opp）：gdx +0.667R(n=15), gld +0.421R(n=19), qqq +0.324R(n=17), spy +0.275R(n=20)
弱：**tlt -0.519R(n=27)** ⚠️, nvda -0.203R(n=16), xlk -0.028R(n=18)

tlt 是个反常的负 EV 大池，建议要么屏蔽要么细查（可能 PA H2 在长债收益率 dynamics 下水土不服）。

### 3. CN_BOND 是个 free win

CN_BOND（cffex_tf 5年国债 / cffex_t 10年 / cffex_ts 2年）n=31, EV +0.548R，3 fold 全正（F2 高达 +1.500R）。这个 lane 在 `pa_detector.py` 的 policy_weight 里完全没出现，应至少加 0.70 weight。

样本量比 CN_METAL（n=46）小但 EV 反而高，TR phase 占绝对主导（28/31）。

### 4. CN_COMMODITY 的 BULL phase 排除几乎无价值

CN_METAL BULL phase 占 7/46（15%），EV -0.026R，排除可以小幅改善。
**CN_COMMODITY BULL phase 占 5/183（3%），EV -0.300R，但样本太少**，排除前后 EV 几乎不变（+0.044R → +0.054R）。

所以 BULL exclusion 在 CN_METAL 上是真值，在 CN_COMMODITY 上是噪声。

## 工程注记

P3 顺手做了：把 Parquet-fallback-JSON 的 load_bars 模式（cn_structural 已用）**抽到 `data/bar_loader.py` 的 `load_bars_quant_or_json()`** 公用 helper，并把 9 个 backtest_pa_* 脚本全部切换过去。`140 passed` 测试套件保护正确性。

```python
# 新 helper — 一处定义，所有脚本共用
def load_bars_quant_or_json(symbol, suffix, fallback_dir, *, quant_root=None):
    """Try Parquet first (BarStore), fall back to legacy JSON."""
```

## 下一步建议

1. **policy table 应该加 CN_BOND**（pa_detector.py docstring 与代码同步）
2. **czce/cn_agri 0.0 weight 验证**：跑 pa_cn_phasefilter 改 POOLS 加 CZCE_ONLY / DCE_AGRI_ONLY sub-pool，或写 sub-pool 切片脚本
3. **US daily vs 60min decisioning**：决定 `score_today` 在 US 走哪条路径（影响生产 weight）
4. **tlt 异常**：要么屏蔽要么深查
5. **n<50/fold 的 lane**（US uptrend+h=opp F2 n=24、CN_BOND n=31）：考虑加 60min/15min 数据扩样

## 代码

- 新增公用 helper: `data/bar_loader.py::load_bars_quant_or_json`
- 切换到 helper 的脚本: pa_cn_structural, pa_swing, pa_us_k3, pa_us_structural, pa_cn_phasefilter, pa_incycle, pa_standalone, pa_context, pa_incremental, pa_15min_confirm

输出 CSV：
- `/tmp/pa_us_k3.csv` (us_equity daily, 996 trades)
- pa_cn_phasefilter 未持久化（建议加 `--out`）
