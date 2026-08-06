# ⚡ NDX Momentum Hedge / 纳斯达克100动量对冲策略

> A Nasdaq-100 momentum stock selection strategy with PSQ 1x inverse QQQ hedge. Weekly rebalance. 5-year backtest +508.5% CAGR 38.9%.
>
> 一个纳斯达克100动量选股 + PSQ一倍做空QQQ对冲策略。周频调仓。5年回测 +508.5%，年化CAGR 38.9%。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python](https://img.shields.io/badge/Python-3.10+-blue)
![Flask](https://img.shields.io/badge/Flask-3.0+-green)

---

## 📖 Table of Contents / 目录

- [Strategy / 策略](#strategy--策略)
- [Backtest / 回测](#backtest--回测)
- [Live Dashboard / 在线看板](#live-dashboard--在线看板)
- [Run Locally / 本地运行](#run-locally--本地运行)
- [Data Sources / 数据来源](#data-sources--数据来源)
- [Support / 打赏](#support--打赏)
- [License / 许可](#license--许可)

---

## Strategy / 策略

### Core Logic / 核心逻辑

1. **Filter** — Select Nasdaq-100 stocks with 20-day momentum > 0 (trend confirmed).
2. **Rank** — Sort by 5-day momentum (recent acceleration).
3. **Pick Top K** — Top 5 stocks, equal weight. Weekly rebalance.
4. **Hedge** — Equal notional in PSQ.US (1x inverse QQQ ETF).

**Stock selection**: 方案B（20日动量>0过滤 + 5日动量排序），取前5只等权做多，对等名义做多PSQ对冲，周频调仓。

> ⚠️ The strategy is designed for **positive momentum** environments. PSQ daily reset decay is accounted for (but over weekly rebalancing the tracking is tight).
>
> ⚠️ 策略仅适用正动量环境。PSQ存在每日重置衰减（但周频调仓下跟踪紧密）。

---

## Backtest / 回测

2021-06 → 2026-08, initial $10,000 / 初始 $10,000：

| Year | Strategy | QQQ | Alpha |
|---|---|---|---|
| 2021 (6m) | +22.5% | +17.0% | +5.5% |
| 2022 | +26.9% | -29.4% | +56.3% |
| 2023 | +35.8% | +53.4% | -17.6% |
| 2024 | +41.4% | +31.5% | +9.9% |
| 2025 | +33.4% | +21.5% | +11.9% |
| 2026 (8m) | +42.2% | +14.7% | +27.5% |
| **Total** | **+508.5%** | **+116.8%** | **+391.7%** |

| Metric | Strategy | QQQ |
|---|---|---|
| CAGR | 38.9% | 15.1% |
| Sharpe | 2.35 | 0.57 |
| Max Drawdown | 9.0% | 35.1% |
| Final ($10k) | $60,850 | $21,685 |

---

## Live Dashboard / 在线看板

https://wepoets1107.github.io/ndx-momentum-hedge/

> Enable in repo Settings → Pages → Source: `main` branch `/docs` folder.
> 仓库 Settings → Pages → Source 选择 main 分支 /docs 目录即可。

---

## Run Locally / 本地运行

```bash
# 1. Clone
git clone https://github.com/wepoets1107/ndx-momentum-hedge.git
cd ndx-momentum-hedge

# 2. Install / 安装
pip install flask requests

# 3. Run / 运行
python server.py   # → http://localhost:5056

# 4. Build static / 生成静态快照
python build.py    # → docs/index.html
```

---

## Data Sources / 数据来源

- **Stock pool / 股票池**：Backpack Exchange public API (`/api/v1/securities`), no key required / 公共接口无需密钥
- **Price data / 价格数据**：Yahoo Finance public crumb, no API key / 公共管道无需密钥
- **Backtest / 回测数据**：Pre-computed weekly data cached in `backtest_5y.json` / 预计算周线数据

---

## Support / 打赏

If this project helps you, consider supporting the community:

如果这个项目对你有帮助，欢迎打赏支持冰火岛社区发展：

```
EVM: 0x29f091DAA3dfee8100645ee24239bCC3ae174B42
```

---

## License / 许可

MIT License. See [LICENSE](LICENSE).

---

*Built for the community by [冰火岛](https://binghuodao.club). Use at your own risk — always test in dry-run mode first.*
*由冰火岛社区开发维护。请自行承担交易风险，务必先以演练模式测试。*
