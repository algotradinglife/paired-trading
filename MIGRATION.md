# Migration record for macd-momentum

迁移时间：2026-06-07T15:49:22+08:00
档位：A
源：/Volumes/Data Drive/workspace/trading/macd-momentum
目标：/Users/huhan/code/trading/macd-momentum

## 数据路径映射

| 旧路径（仓内） | 新路径（外置盘） |
| --- | --- |
| `src/data/quant/SHFE` | `/Volumes/Data Drive/data/futures/macd-momentum/quant/SHFE` |
| `src/data/quant/DCE` | `/Volumes/Data Drive/data/futures/macd-momentum/quant/DCE` |
| `src/data/quant/CZCE` | `/Volumes/Data Drive/data/futures/macd-momentum/quant/CZCE` |
| `src/data/quant/CFFEX` | `/Volumes/Data Drive/data/futures/macd-momentum/quant/CFFEX` |
| `src/data/quant/INE` | `/Volumes/Data Drive/data/futures/macd-momentum/quant/INE` |
| `src/data/quant/NYSE` | `/Volumes/Data Drive/data/stock/macd-momentum/quant/NYSE` |
| `src/data/quant/_contracts` | `/Volumes/Data Drive/data/futures/macd-momentum/quant/_contracts` |
| `src/data/options/cn` | `/Volumes/Data Drive/data/futures/macd-momentum/options/cn` |
| `src/data/options/dia` | `/Volumes/Data Drive/data/stock/macd-momentum/options/dia` |
| `src/data/options/gld` | `/Volumes/Data Drive/data/stock/macd-momentum/options/gld` |
| `src/data/options/xlk` | `/Volumes/Data Drive/data/stock/macd-momentum/options/xlk` |
| `src/data/options/gdx` | `/Volumes/Data Drive/data/stock/macd-momentum/options/gdx` |
| `src/data/options/tlt` | `/Volumes/Data Drive/data/stock/macd-momentum/options/tlt` |
| `src/data/options/xlf` | `/Volumes/Data Drive/data/stock/macd-momentum/options/xlf` |
| `src/data/options/nvda` | `/Volumes/Data Drive/data/stock/macd-momentum/options/nvda` |
| `src/data/options/iwm` | `/Volumes/Data Drive/data/stock/macd-momentum/options/iwm` |
| `src/data/options/spy` | `/Volumes/Data Drive/data/stock/macd-momentum/options/spy` |
| `src/data/raw` | `/Volumes/Data Drive/data/futures/macd-momentum/raw` |
| `src/data/review` | `/Volumes/Data Drive/derived/macd-momentum/src-data-review` |
| `src/data/quant_minishare_main` | `/Volumes/Data Drive/data/futures/macd-momentum/quant_minishare_main` |
| `data/review` | `/Volumes/Data Drive/derived/macd-momentum/data-review` |

## 改代码（待人手）

请把硬编码的老路径替换为环境变量。嫌疑位置见 plan.yaml 的 hardcoded_path_hits 字段。
