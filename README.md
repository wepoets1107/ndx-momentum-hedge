# NDX Momentum Hedge / 纳斯达克100动量对冲策略

> 方案B：20日动量>0过滤 + 5日动量排序，K=5 + PSQ等名义对冲，周频调仓。
> 5年回测 +508.5%（年化CAGR 38.9%），最大回撤9%。

## Live Dashboard

https://wepoets1107.github.io/ndx-momentum-hedge/

（在 GitHub 仓库 Settings → Pages → Source 选择 main 分支 /docs 目录即可启用）

## Run Locally

```bash
pip install flask requests
python server.py  # → http://localhost:5056
python build.py   # 生成静态 HTML → docs/index.html
```

## Data Sources

- 股票池：Backpack Exchange public API（`/api/v1/securities`，无需 API key）
- 价格数据：Yahoo Finance（public crumb，无需 API key）
- 回测数据：2021-2026 周线，预计算缓存 `backtest_5y.json`

## License

MIT
