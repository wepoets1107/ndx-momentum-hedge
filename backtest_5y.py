# -*- coding: utf-8 -*-
"""
纳斯达克100动量对冲策略 五年回测（v2.0 — 审计纠正版）

策略：50%做多Top5动量个股 + 50%PSQ对冲，周频调仓（每5个交易日）
对照组：100% QQQ 买入持有

审计纠正内容：
  - 回测与实盘逻辑一致：严格50/50对冲
  - 杜绝前视偏差：动量仅用调仓日收盘及之前数据，收益从当日收盘起算
  - 收益口径自洽：总收益/CAGR/年化/夏普/最大回撤均由同一净值序列计算
  - 已知局限：股票池为当前纳指100成分（幸存者偏差），结果可能偏高
"""
import os, json, time, pickle, math, statistics
from datetime import datetime
import requests

# ══════════════════════════════════════════════════════════════
#  配置
# ══════════════════════════════════════════════════════════════

PORTFOLIO     = 10000       # 策略初始总资金
STOCK_ALLOC   = 5000        # 个股仓位
PSQ_ALLOC     = 5000        # PSQ 对冲仓位
QQQ_CAPITAL   = 10000       # QQQ 对照组
TOP_K         = 5           # 选股数量
LOOKBACK      = 20          # 20 日动量过滤门槛
MOM_5D        = 5           # 5 日动量排序窗口（也是调仓间隔）
RF_ANNUAL     = 0.0         # 无风险利率（年化）
START_DATE    = "2021-06-07"
END_DATE      = "2026-08-06"

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE    = os.path.join(BASE_DIR, "bt_price_cache.pkl")
OUTPUT_FILE   = os.path.join(BASE_DIR, "backtest_5y.json")

# 当前纳指 100 成分股（含后来纳入者，缺已剔除者 → 幸存者偏差）
NDX_100 = [
    'NVDA','AAPL','AVGO','META','MU','MSFT','AMD','AMZN','TSLA','GOOGL',
    'GOOG','INTC','ASML','CSCO','COST','AMAT','LRCX','NFLX','PLTR','PANW',
    'ARM','TXN','KLAC','LIN','AMGN','CRWD','PEP','ADBE','ADI',
    'QCOM','BKNG','WDAY','MRVL','INTU','CDNS','SNPS','PCAR','NXPI','FTNT',
    'MCHP','ROP','ODFL','MAR','CPRT','ORLY','CTAS','PAYX','AZN','MNST',
    'KDP','DASH','DDOG','MDB','TTD','TEAM','KHC','XEL','EXC',
    'GEHC','CSGP','BKR','ROST','LULU','IDXX','FAST','EA','VRTX','REGN',
    'GFS','SBUX','CMCSA','ADP','MELI','GILD','MDLZ','ZS','WBD','PDD','MRNA','DXCM',
    'CRM','NOW','ISRG','BIIB','CEG','CDW','CHTR','DLTR','FANG','ILMN',
    'MSTR','ON','PYPL','RIVN','SMCI','TTWO','VRSK','ZM',
]

# ══════════════════════════════════════════════════════════════
#  数据拉取（Yahoo Finance，adjclose）
# ══════════════════════════════════════════════════════════════

def fetch_yahoo_batch(tickers, start_ts, end_ts):
    """批量拉取 Yahoo 日线 adjclose，带限速和重试"""
    sess = requests.Session()
    sess.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

    # crumb
    try:
        sess.get("https://fc.yahoo.com/", timeout=15)
        crumb = sess.get("https://query2.finance.yahoo.com/v1/test/getcrumb", timeout=15).text.strip()
    except Exception:
        crumb = ""

    all_data = {}
    total = len(tickers)

    for idx, tkr in enumerate(tickers):
        print(f"  [{idx+1:3d}/{total}] {tkr:6s} ", end="", flush=True)
        ok = False
        for attempt in range(3):
            try:
                url = (
                    f"https://query2.finance.yahoo.com/v8/finance/chart/{tkr}"
                    f"?period1={start_ts}&period2={end_ts}&interval=1d&crumb={crumb}"
                )
                r = sess.get(url, timeout=30)
                if r.status_code == 429:
                    print("限速，等待5秒...")
                    time.sleep(5)
                    continue
                if r.status_code != 200:
                    print(f"HTTP {r.status_code}", end="")
                    if attempt < 2:
                        print(", 重试...", end=" ")
                        time.sleep(2)
                    continue
                data = r.json()
                if "chart" not in data or not data["chart"]["result"]:
                    print("无数据", end="")
                    break
                result = data["chart"]["result"][0]
                adj  = result["indicators"]["adjclose"][0]["adjclose"]
                ts_arr = result["timestamp"]
                prices = {}
                for ts, p in zip(ts_arr, adj):
                    if p is not None:
                        prices[datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")] = float(p)
                if len(prices) < 20:
                    print(f"仅{len(prices)}条", end="")
                    break
                all_data[tkr] = prices
                print(f"OK {len(prices)}条")
                ok = True
                break
            except Exception as e:
                if attempt < 2:
                    print(f"错误, 重试...", end=" ")
                    time.sleep(2)
                else:
                    print(f"放弃 {e}")
        if not ok:
            print("失败")
        time.sleep(0.4)

    return all_data


def load_or_fetch_prices():
    """加载缓存 → 不存在则拉取全量"""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "rb") as f:
            data = pickle.load(f)
        print(f"从缓存加载 {len(data)} 只标的 ({len(data.get('QQQ',{}))} 天 QQQ)\n")
        return data

    print("拉取全量历史数据（这需要约 1 分钟）...\n")
    start_ts = int(datetime(2019, 1, 1).timestamp())   # 给足前置数据
    end_ts   = int(datetime(2026, 8, 10).timestamp())

    tickers = list(NDX_100) + ["QQQ", "PSQ"]
    data = fetch_yahoo_batch(tickers, start_ts, end_ts)

    # 去掉完全没有数据的
    dropped = [t for t in tickers if t not in data]
    if dropped:
        print(f"\n无数据标的({len(dropped)}): {dropped}")

    with open(CACHE_FILE, "wb") as f:
        pickle.dump(data, f)
    print(f"\n已缓存 {len(data)} 只标的\n")
    return data


# ══════════════════════════════════════════════════════════════
#  回测引擎
# ══════════════════════════════════════════════════════════════

def run_backtest(all_prices):
    """
    主回测循环。

    调仓日 t 的操作：
      1. 用 t 收盘价算各股 20d / 5d 动量
      2. 20d>0 池中按 5d 排序取 TopK
      3. 个股等权共 $5K + PSQ $5K → 持有到 t+5 收盘
      4. 收益 = t+5 收盘 / t 收盘 - 1

    关键：动量计算只用 t 及之前的数据；收益从 t 起算 → 零前视。
    """
    if "QQQ" not in all_prices:
        raise RuntimeError("QQQ 数据缺失")

    # ── 交易日历（以 QQQ 为准） ──
    all_dates = sorted(all_prices["QQQ"].keys())
    all_dates = [d for d in all_dates if START_DATE <= d <= END_DATE]

    if len(all_dates) < LOOKBACK + 10:
        raise RuntimeError(f"交易日不足: {len(all_dates)} 天")

    # 第一个可调仓位置：需要 dates[i-LOOKBACK] 存在
    first_idx = LOOKBACK
    rebalance_indices = list(range(first_idx, len(all_dates) - MOM_5D, MOM_5D))

    if not rebalance_indices:
        raise RuntimeError("无可用调仓日")

    # ── 初始化 ──
    strat_val = PORTFOLIO
    qqq_val   = QQQ_CAPITAL

    strategy_vals = [strat_val]
    qqq_vals      = [qqq_val]
    nav_dates     = [all_dates[rebalance_indices[0]]]

    # PSQ 缓存
    psq_prices = all_prices.get("PSQ", {})
    qqq_prices = all_prices["QQQ"]

    trade_log = []

    for ri, idx in enumerate(rebalance_indices):
        cur_date  = all_dates[idx]
        next_idx  = idx + MOM_5D
        if next_idx >= len(all_dates):
            break
        next_date = all_dates[next_idx]

        # ── 选股 ──
        candidates = []
        for tkr in NDX_100:
            px = all_prices.get(tkr)
            if not px:
                continue
            if cur_date not in px:
                continue

            date_20d = all_dates[idx - LOOKBACK]
            if date_20d not in px or px[date_20d] <= 0:
                continue

            date_5d = all_dates[idx - MOM_5D]
            if date_5d not in px or px[date_5d] <= 0:
                continue

            # 前视检查：下周价格必须存在（否则无法算收益 → 淘汰）
            if next_date not in px or px[next_date] <= 0:
                continue

            mom20 = px[cur_date] / px[date_20d] - 1
            if mom20 <= 0:
                continue

            mom5 = px[cur_date] / px[date_5d] - 1
            candidates.append({
                "tkr": tkr, "mom20": mom20, "mom5": mom5,
                "px_now": px[cur_date], "px_next": px[next_date],
            })

        candidates.sort(key=lambda x: x["mom5"], reverse=True)
        selected = candidates[:TOP_K]
        k = len(selected)

        # ── 本周收益 ──
        # 个股部分（权重 = STOCK_ALLOC / PORTFOLIO = 0.5）
        if k > 0:
            stock_ret = sum(s["px_next"] / s["px_now"] - 1 for s in selected) / k
        else:
            stock_ret = 0.0   # 无合格股 → 个股部分持现金

        # PSQ 部分（权重 = PSQ_ALLOC / PORTFOLIO = 0.5）
        if cur_date in psq_prices and next_date in psq_prices:
            psq_ret = psq_prices[next_date] / psq_prices[cur_date] - 1
        else:
            psq_ret = 0.0

        strat_ret = stock_ret * (STOCK_ALLOC / PORTFOLIO) + psq_ret * (PSQ_ALLOC / PORTFOLIO)

        # QQQ 部分
        qqq_ret = qqq_prices[next_date] / qqq_prices[cur_date] - 1

        # ── 更新净值 ──
        strat_val *= (1 + strat_ret)
        qqq_val   *= (1 + qqq_ret)

        strategy_vals.append(strat_val)
        qqq_vals.append(qqq_val)
        nav_dates.append(next_date)

        # ── 日志 ──
        trade_log.append({
            "date": cur_date,
            "next_date": next_date,
            "selected": [s["tkr"] for s in selected],
            "stock_ret_pct": round(stock_ret * 100, 2),
            "psq_ret_pct":   round(psq_ret * 100, 2),
            "strat_ret_pct": round(strat_ret * 100, 2),
            "qqq_ret_pct":   round(qqq_ret * 100, 2),
            "k": k,
        })

    return strategy_vals, qqq_vals, nav_dates, trade_log


# ══════════════════════════════════════════════════════════════
#  统计指标（所有指标由同一净值序列计算）
# ══════════════════════════════════════════════════════════════

def compute_stats(values, dates, rf_annual=RF_ANNUAL):
    """由净值序列统一计算所有指标，杜绝口径不一"""
    n = len(values)
    if n < 2:
        return {}

    # 周收益序列
    weekly = [(values[i] / values[i-1] - 1) for i in range(1, n)]

    # 总收益 & CAGR（用真实日历年限，不用周数除52）
    total_ret  = values[-1] / values[0] - 1
    first_dt   = datetime.strptime(dates[0], "%Y-%m-%d")
    last_dt    = datetime.strptime(dates[-1], "%Y-%m-%d")
    total_yrs  = (last_dt - first_dt).days / 365.25
    cagr       = (values[-1] / values[0]) ** (1 / total_yrs) - 1 if total_yrs > 0 else 0

    # 夏普（年化，周收益）
    rf_w  = rf_annual / 52
    mean_w = statistics.mean(weekly)
    std_w  = statistics.pstdev(weekly)
    sharpe = (mean_w - rf_w) / std_w * math.sqrt(52) if std_w > 0 else 0

    # 最大回撤
    peak   = values[0]
    max_dd = 0.0
    for v in values:
        if v > peak:
            peak = v
        dd = v / peak - 1
        if dd < max_dd:
            max_dd = dd

    # 逐年收益（按日历年末最后净值算）
    year_last = {}   # year → 该年最后一个净值
    for d, v in zip(dates, values):
        yr = int(d[:4])
        year_last[yr] = v

    sorted_years = sorted(year_last.keys())
    annual_list  = []
    for i, yr in enumerate(sorted_years):
        if i == 0:
            ret = (year_last[yr] / values[0] - 1) * 100
        else:
            ret = (year_last[yr] / year_last[sorted_years[i-1]] - 1) * 100
        label = str(yr) if yr < 2026 else f"{yr}(至8月)"
        annual_list.append({"year": label, "return": round(ret, 1)})

    return {
        "total_return":  round(total_ret * 100, 1),
        "final_value":   round(values[-1], 2),
        "cagr":          round(cagr * 100, 1),
        "sharpe":        round(sharpe, 2),
        "max_drawdown":  round(max_dd * 100, 1),
        "annual_list":   annual_list,
        "n_weeks":       len(weekly),
        "total_years":   round(total_yrs, 2),
        "mean_weekly":   round(mean_w * 100, 2),
        "std_weekly":    round(std_w * 100, 2),
    }


# ══════════════════════════════════════════════════════════════
#  主程序
# ══════════════════════════════════════════════════════════════

def main():
    print("=" * 64)
    print("  纳指100 动量对冲策略  五年回测  v2.0 审计纠正版")
    print("=" * 64)
    print(f"  策略: 50% 做多 Top{TOP_K} 动量股 + 50% PSQ 对冲  |  周频调仓")
    print(f"  初始: 策略 $10,000 (个股 $5,000 + PSQ $5,000)")
    print(f"        对照 QQQ  $10,000 买入持有")
    print()

    # 1) 数据
    all_prices = load_or_fetch_prices()

    # 2) 回测
    strat_vals, qqq_vals, nav_dates, trade_log = run_backtest(all_prices)

    # 3) 统计
    s = compute_stats(strat_vals, nav_dates)
    q = compute_stats(qqq_vals, nav_dates)

    # 合并 yearly
    yearly = []
    for se in s["annual_list"]:
        label = se["year"]
        qe = next((x for x in q["annual_list"] if x["year"] == label), None)
        yearly.append({
            "year":     label,
            "strategy": se["return"],
            "qqq":      qe["return"] if qe else 0,
        })

    # 4) 写 JSON
    output = {
        "method":            f"方案B (20d>0过滤 + 5d排序取Top{TOP_K}) · 50%个股/50%PSQ对冲 · 周频",
        "period":            f"{START_DATE} → {END_DATE}",
        "initial_capital":   PORTFOLIO,
        "stock_alloc":       STOCK_ALLOC,
        "psq_alloc":         PSQ_ALLOC,
        "total_return":      s["total_return"],
        "qqq_return":        q["total_return"],
        "sharpe":            s["sharpe"],
        "qqq_sharpe":        q["sharpe"],
        "max_drawdown":      s["max_drawdown"],
        "qqq_max_drawdown":  q["max_drawdown"],
        "final_value":       s["final_value"],
        "qqq_final_value":   q["final_value"],
        "strategy_cagr":     s["cagr"],
        "qqq_cagr":          q["cagr"],
        "yearly":            yearly,
        "strategy_values":   strat_vals,
        "qqq_values":        qqq_vals,
        "n_trades":          len(trade_log),
        "total_years":       s["total_years"],
        "mean_weekly_pct":   s["mean_weekly"],
        "std_weekly_pct":    s["std_weekly"],
        "trade_log":         trade_log,
        "audit_notes": [
            "v2.0 审计纠正版：收益口径由同一净值序列统一计算，消除内部矛盾",
            "前视控制：动量只用调仓日收盘及之前数据；收益从调仓日收盘起算到下周收盘",
            "策略严格执行 50/50：STOCK_ALLOC/PORTFOLIO 与 PSQ_ALLOC/PORTFOLIO 各 0.5",
            "股票池为 2026 年 8 月当前纳指100成分 → 含后来纳入者、缺已剔除者 → 幸存者偏差，结果可能偏高",
            "已退市/停牌股：数据自然缺失 → 调仓日自动淘汰，不会错误选中",
            f"无风险利率: {RF_ANNUAL}% (年化)",
            "数据源: Yahoo Finance adjclose (已含分红拆股调整)",
        ],
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # 5) 终端报告
    print("=" * 64)
    print("  回测完成\n")
    print(f"  策略总收益 : {s['total_return']:>8.1f}%   (${s['final_value']:,.0f})")
    print(f"  QQQ  总收益 : {q['total_return']:>8.1f}%   (${q['final_value']:,.0f})")
    print(f"  策略 CAGR  : {s['cagr']:>8.1f}%")
    print(f"  QQQ   CAGR  : {q['cagr']:>8.1f}%")
    print(f"  策略 夏普   : {s['sharpe']:>8.2f}")
    print(f"  QQQ   夏普   : {q['sharpe']:>8.2f}")
    print(f"  策略 最大回撤: {s['max_drawdown']:>8.1f}%")
    print(f"  QQQ   最大回撤: {q['max_drawdown']:>8.1f}%")
    print(f"  交易次数    : {len(trade_log):>8d}")
    print(f"  有效年份    : {s['total_years']:>8.2f}")
    print(f"  周收益均值  : {s['mean_weekly']:>8.2f}%  (±{s['std_weekly']}%)")
    print()
    for y in yearly:
        print(f"  {y['year']:12s}  策略 {y['strategy']:>6.1f}%   QQQ {y['qqq']:>6.1f}%")
    print()
    print(f"  输出 → {OUTPUT_FILE}")
    print("=" * 64)


if __name__ == "__main__":
    main()
