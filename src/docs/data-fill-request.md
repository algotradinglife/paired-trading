# 数据补齐需求 — paired-trading → quant-data

**日期**: 2026-06-02  
**提出方**: paired-trading 项目（旧称 macd-momentum）  
**接收方**: quant-data 项目  
**背景**: 期权 payoff 分析管道已打通（3,111 条 CN 期权记录），但存在三类数据缺口导致关键分析单元格样本量不足，无法进行统计检验。

---

## 现状诊断

### 可运行的基线

```
analyze_options_payoff.py --source parquet --market CN
→ 3,111 条记录，2,739 条匹配信号
→ bottom × opposing × call × h5_ret: n=157, mean=+1.211R, pct>0=50%
→ 其中 rank=1-4: n=58, mean=+2.036R（优质但 CI 太宽）
→ 其中 rank=null: n=30, mean=+0.508R, CI=[+0.047, +0.968]（CI 不跨零，唯一统计显著）
```

### 三个核心缺口

| 缺口 | 当前状态 | 影响 |
|------|---------|------|
| OTM rank 缺失 | 1,402/3,111 条（45%）无 rank | 无法做分层收益分析 |
| h=20 数据空白 | bottom×opp×call h20_ret 仅 n=6 | 无法评估长持有期策略 |
| CN_AGRI 期权稀少 | 44 个合约 vs CN_METAL 3,078 个 | CZCE/DCE 信号无期权对应 |

---

## 需求一：OTM Rank 补全（P0 — 最高优先级）

### 问题

`_contracts/SHFE.parquet`、`DCE.parquet`、`CZCE.parquet` 已有 `option_strike` 和 `option_underlying` 字段，但 paired-trading 的 payoff 分析脚本无法自动计算 OTM rank（需要信号日期当天的标的收盘价）。

现有 `_contracts` schema：

```
symbol            str       # e.g. AG2510C10100
option_strike     float64   # e.g. 10100.0
option_type       str       # "call" / "put"
option_expiry     object    # e.g. "2025-09-19"
option_underlying str       # e.g. "ag0.SHFE"
option_portfolio  str       # e.g. "AG"
```

### 需求

在 `_contracts/*.parquet` 中，或作为单独的查找表，提供每个合约在**每个信号日期**的 OTM rank。

**定义**：OTM rank = 该合约行权价距离当日标的收盘价的档位，按与 ATM 的距离从近到远排序，rank=1 为最近虚值（第一档 OTM），rank=2 为第二档，以此类推。

方案 A（推荐）：在 `_contracts/*.parquet` 中新增两列：

```
atm_strike    float64   # 每个到期月在上市首日的 ATM 行权价（静态参考点）
strike_step   float64   # 行权价间距（e.g. AG=100, RB=50, AU=4）
```

paired-trading 端根据这两列 + 信号日期的标的价格自行计算当日 OTM rank，无需逐日数据。

方案 B：提供 `_otm_rank/{exchange}.parquet`，schema：

```
symbol        str
date          date
otm_rank      int8    # 1=最近虚值，0=平值，-1=实值最近档，以此类推
atm_dist_pct  float64 # (strike - underlying_close) / underlying_close
```

### 覆盖范围

所有已入库的 SHFE/DCE/CZCE 期权合约（3,122 个），信号日期范围 2021-01-01 至今。

### 预期效果

- rank=null 比例从 45% → <5%
- bottom×opposing×call rank=1-4 可用样本从 n=58 → ~n=130
- 每个 rank 格达到 n≥30，CI 可收窄至显著水平

---

## 需求二：h=20 持有期数据补全（P1）

### 问题

bottom×opposing×call h20_ret 目前只有 n=6，原因是大量合约在信号日期后不足 20 个交易日就到期或停止交易。

通过查询发现，存量数据中很多合约只有 1-10 条 daily bar（如 AU2105C352 只有 1 条），是近月合约末期数据。

### 需求

**调整数据抓取策略**：对于每个信号日期，优先保证有**下一个到期月（近月+1 或中月）** 的合约数据，而不只是最近到期的合约。具体要求：

1. 对每个标的，确保至少有一个合约在信号日期后还有 **≥25 个交易日（约 35 个日历日）** 的存续期。
2. 如果只有当月合约且剩余天数 <25 交易日，补充下月合约数据。

### 格式要求

无格式变化，仍为 `daily.parquet`，schema 同现有：

```
datetime        datetime64[us, UTC]
open_price      float64
high_price      float64
low_price       float64
close_price     float64
volume          float64
amount          float64
open_interest   float64
```

### 优先覆盖品种

按信号量排序（bottom×opposing×call 当前数据分布）：

| 品种 | 当前 n | 优先级 |
|------|--------|--------|
| SHFE/AU（黄金） | 92 | 高 |
| SHFE/RB（螺纹钢）| 68 | 高 |
| CZCE/SR（白糖） | 15 | 中 |
| SHFE/AG（白银） | 12 | 中 |
| DCE/I（铁矿） | 6 | 中 |

### 预期效果

- h20_ret 可用样本从 n=6 → n≥60
- 完整持有期收益曲线 h5/h10/h20 可用于寻找最优退出点

---

## 需求三：CN_AGRI 期权品种扩展（P1）

### 问题

CN_AGRI 信号池（CZCE + 部分 DCE）在 walk-forward OOS 中有验证通过的信号（CZCE bottom×opp EV=+1.202R），但对应期权数据极其稀少：

```
当前 CN_AGRI 期权覆盖：
  CZCE/CF（棉花）:   1 个合约
  CZCE/MA（甲醇）:   4 个合约
  CZCE/SA（纯碱）:   1 个合约
  CZCE/SR（白糖）:  16 个合约
  CZCE/TA（PTA）:    7 个合约
  DCE/I（铁矿）:     7 个合约
  DCE/J（焦炭）:     1 个合约
  DCE/JM（焦煤）:    1 个合约
  DCE/M（豆粕）:     4 个合约
  DCE/P（棕榈油）:   1 个合约
  DCE/Y（豆油）:     1 个合约
```

对比 CN_METAL（SHFE AU/RB/CU/AG 共 3,078 个合约），差距悬殊。

### 需求

补充以下 CN_AGRI 品种的完整期权历史，目标覆盖范围：**2021-01-01 至今，所有到期月，所有行权价**。

**优先级排序（按信号量 × 流动性）**：

| 品种 | 交易所 | 目标合约数 | 优先级 |
|------|--------|-----------|--------|
| DCE/M（豆粕） | DCE | 500+ | P1 — 豆粕是 DCE 最活跃期权，信号量大 |
| CZCE/SR（白糖）| CZCE | 300+ | P1 — 已有 16 个，缺口最小 |
| CZCE/MA（甲醇）| CZCE | 200+ | P1 |
| DCE/I（铁矿） | DCE | 400+ | P1 — DCE 流动性最好品种之一 |
| CZCE/TA（PTA）| CZCE | 200+ | P2 |
| CZCE/CF（棉花）| CZCE | 150+ | P2 |
| DCE/Y（豆油） | DCE | 200+ | P2 |
| DCE/P（棕榈油）| DCE | 150+ | P2 |
| CZCE/SA（纯碱）| CZCE | 100+ | P3 |
| DCE/J（焦炭） | DCE | 100+ | P3 |
| DCE/JM（焦煤）| DCE | 100+ | P3 |

### 格式要求

与现有 CN_METAL 完全一致：

```
路径: data/quant/{EXCHANGE}/{SYMBOL}/daily.parquet
合约元数据: data/quant/_contracts/{EXCHANGE}.parquet （新增行追加）
```

数据来源建议：TqSdk（已验证可用，symbol 格式已知）。

### 预期效果

- CN_AGRI 期权合约从 44 → 2,000+
- bottom×opposing×call (CZCE 池) 可用样本从 ~30 → 200+
- 可单独验证 CZCE 信号的期权收益，与 CN_METAL 分开统计

---

## 需求四：US 期权数据（P2 — 后续）

### 背景

US ETF 信号池（10 只 ETF）已有 walk-forward OOS 验证（uptrend+h=opposing EV=+0.636R, n=22）。US 期权 payoff 分析目前完全空白。

### 需求

为以下 10 只 ETF 补充期权日线 OHLCV 数据：

```
SPY, QQQ, DIA, IWM, GLD, GDX, TLT, XLF, XLK, NVDA
```

范围：2021-01-01 至今，所有到期月，行权价覆盖 ATM ± 10 档。

格式与 CN 一致，exchange=NYSE，路径 `data/quant/NYSE/{SYMBOL}/daily.parquet`。

数据来源：Polygon Options API（已有代理配置）。

---

## 格式规范汇总

### daily.parquet schema（不变）

```
datetime        datetime64[us, UTC]   # SHFE: 每日 09:00 UTC+8 收盘 → 01:00 UTC
open_price      float64
high_price      float64
low_price       float64
close_price     float64
volume          float64               # 手数
amount          float64               # 成交金额（允许为 0，部分品种不统计）
open_interest   float64
```

### _contracts/{EXCHANGE}.parquet schema（不变，OTM rank 需求另行讨论）

```
symbol            str
exchange          str
product           str       # "option"
option_strike     float64
option_type       str       # "call" / "put"
option_expiry     object    # "YYYY-MM-DD"
option_underlying str       # "rb0.SHFE"
option_portfolio  str       # "RB"
option_listed     object    # 上市日（如有）
option_index      str       # "C3500"
```

---

## 验收标准

完成后 paired-trading 端执行以下命令验收：

```bash
# CN 全量
python scripts/analyze_options_payoff.py --source parquet --market CN \
    -o data/review/option_payoffs_parquet_cn_v2.csv

# 验收指标
# 1. otm_rank null 比例 < 5%
# 2. bottom × opposing × call × h5_ret n ≥ 200（当前 157）
# 3. bottom × opposing × call × h20_ret n ≥ 60（当前 6）
# 4. CN_AGRI 品种在 underlying 分布中有 DCE/M、CZCE/SR、CZCE/MA（当前缺失）
```

---

## 优先级汇总

| 需求 | 优先级 | 工作量估计 | 解锁的分析 |
|------|--------|-----------|-----------|
| OTM rank 补全 | **P0** | 低（计算任务）| rank 分层收益甜区 |
| h=20 持有期数据 | P1 | 中（调整抓取策略）| 完整持有期曲线 |
| CN_AGRI 品种扩展 | P1 | 高（大量合约入库）| CZCE/DCE 期权 payoff |
| US ETF 期权 | P2 | 中 | US 期权策略验证 |

P0 OTM rank 优先级最高，因为是纯计算任务（数据已在库），工作量最小，但解锁的样本量提升最大（45% 无效数据变为有效）。
