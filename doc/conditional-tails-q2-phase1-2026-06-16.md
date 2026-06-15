# Q2-Phase1：配对边缘的「条件凸性」实测（2026-06-16）

承接 philosopher worth-triage（[[option-pairing-edge-triage-2026-06-16]]，card t_49029cd2）。
**假设**：在已验证方向信号上加 call，唯一付得起 theta+点差的理由是捕获标的**条件右尾凸性**；
贵金属(ag/au)右尾肥于基本金属(cu/rb)，解释 DD-line 的 ag/au EV+ vs cu/rb EV−。
**Phase 1（免费、无新数据）**：用现有 R 空间 corpus（rb/cu/au，au 代表贵金属；ag 待数据）实测
每品种**信号后条件前向分布**，把「上涨偏态」从口头归因变成可测统计量。

工具 `scripts/analyze_conditional_tails.py`（复用 canonical 取数 `_load_cn_window` + 同 SPEC-001 突破选择；
从信号棒收盘 S0 起、固定前向 horizon H 内测**未封顶**路径：MFE/MAE/terminal，ATR 单位）。
**机械统计，研究性，不打 PASS/FAIL。** 复现：
`cd src && ./.venv/bin/python scripts/analyze_conditional_tails.py --corpus data/review/pa_dataset_rbcuau.labeled.jsonl`

## 关键方法学纠正：excursion 右尾 ≠ 凸性
MFE/MAE（窗口内最大顺/逆行）**被波动率主导、近似对称**：全品种 MFE 均值 8–18 ATR、
P[MFE≥2]≈P[MAE≥2]、asym≈1.0–1.1。这是任何扩散过程的必然（excursion∼σ√H），**不分辨品种、不反映信号凸性**。
→ 决策相关量改用 **terminal 期权回报代理** `E[max(term−k,0)]`（k-ATR-OTM call 在 H 处的内在价值，ATR 单位），
及其 put 镜像 `E[max(−term−k,0)]`。**call/put@k1 比率**（>1=右尾/call 占优）是跨品种可比的配对适配判据。

## 结果（all-candidate 结构性总体，n≈990–1180/品种，统计有力）
> 注：初版单一 8000-bar 窗口会丢早期信号（au 月合约交易约 380 天≈80k 5min bar，codex P2）；
> 已修为按各合约**全候选跨度**取数，coverage no_s0=0（无早期丢弃），仅合约末端 short_horizon 丢弃。
> 修正后 au 凸性更强，定性结论不变。

| 品种 | call/put@k1 (H=96) | call/put@k1 (H=288) | terminal skew (H=288) | terminal drift (H=288) |
|---|---|---|---|---|
| **au**（贵金属） | **1.64** | **1.65** | **+0.50**（唯一正） | +3.32 |
| **cu**（基本） | **1.43** | **1.55** | −0.75 | +3.07 |
| **rb**（基本） | 1.04 | **0.93** | −0.51 | −0.38 |

- **au：明确 call 凸性占优**（call/put 1.64–1.65，唯一正偏度）→ ✓ 支持假设。
- **rb：近对称→偏 put**（call/put 0.93–1.04，负漂移）→ ✓ rb 确实缺 call 凸性，与 DD-line rb 负 EV 一致。
- **cu：也明显 call 占优**（1.43–1.55，drift 驱动，尽管偏度负）→ ✗ **与「基本金属没有」相矛盾**。

## 诚实结论
1. **「贵金属 vs 基本金属」二分太粗**：真正的分界是**逐品种前向漂移/凸性**——au 与 cu 同属 call 占优、rb 另一类。
   不是 precious/base，是 per-instrument。
2. **标的前向分布解释了 au+ / rb−，但解释不了 cu−**：cu 标的层 call 凸性favorable，DD-line 期权却 EV−
   → 差异必来自**期权侧（IV/theta 太贵相对其 realized 凸性）**。**这恰恰证明 Phase 2（realized vs implied）
   是必需的，且把 cu 钉成关键判例**：若 cu 的隐含凸性 > realized，则「便宜凸性」判据成立、cu 被正确排除。
3. **excursion 右尾质量是错误度量**（vol 主导）；terminal call-payoff 才是配对适配的正确量。
4. **Q3 put：结构性 de-prioritize 成立**——au/cu put_payoff < call_payoff，rb 近对称，无品种结构性偏 put
   （与 philosopher 先验 + PA-top 镜像否决一致）。

## 强 caveat
- **spec（replica 选中）子集 n 太小（15–41）且 au 子集自相矛盾**：au-spec call/put≈0.5（负漂移，n=15），
  rb-spec 强正——与 DD-line 排序相反。几乎确定是小样本噪声 +（可能）窗口/horizon 与 DD-line 期权持有口径不一致。
  **可靠读数是 all-candidate 结构性总体**；spec 子集仅记录、不下结论。
- 全为**标的前向分布**，未含 IV/theta；真实期权 EV（DD-line）须 Phase 2。
- au 是唯一贵金属代表；ag 待数据（另案）才能确认 precious 共性。

## 下一步
- **Phase 2（需期权数据，另起 data 卡）**：ag/au/cu/rb 在**信号时点**的 OTM call IV/skew（或 ATM IV + 25Δ RR），
  比 realized 凸性 vs implied。**优先验 cu**（标的 call-favorable 却期权 EV−，是「便宜凸性」判据的判例）。
- 当前 data 卡 t_f68f93e2 是闸门 OOS（al/zn/ni/ag/i 5min 标的），**与本 Phase 2 无关**；Phase 2 数据另需。

工件 `data/review/conditional_tails.json`（gitignore）。
相关：[[option-pairing-edge-triage-2026-06-16]]、[[project_ddline_options_findings]]、[[project_spec001_ev_eval]]。
