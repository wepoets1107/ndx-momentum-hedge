# -*- coding: utf-8 -*-
"""
纳斯达克100动量选股 + PSQ对冲策略 — Flask后端
端口 5056 | 数据来源 Yahoo Finance + Backpack
"""
import time, json, os, pickle, threading
from datetime import datetime, timedelta
import requests
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

PORT = 5056
TOP_K = 5
LOOKBACK = 20
DATA_FILE = os.path.join(os.path.dirname(__file__), "report_cache.json")
PRICE_CACHE = os.path.join(os.path.dirname(__file__), "price_cache.pkl")
BT_FILE = os.path.join(os.path.dirname(__file__), "backtest_5y.json")
TEMPLATE = os.path.join(os.path.dirname(__file__), "templates", "dashboard.html")

# ==== 股票池 ====
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

def get_bpx_tradable():
    try:
        resp = requests.get("https://api.backpack.exchange/api/v1/securities", timeout=10)
        bpx_set = {s["asset"].replace(".US","") for s in resp.json()}
        return sorted([t for t in NDX_100 if t in bpx_set])
    except:
        return sorted(NDX_100)

def yahoo_prices(tickers):
    """拉取 Yahoo Finance 价格数据，缓存 2 小时"""
    now = time.time()
    if os.path.exists(PRICE_CACHE):
        with open(PRICE_CACHE, "rb") as f:
            cache = pickle.load(f)
        if now - cache.get("_ts", 0) < 7200:
            return cache["data"]

    sess = requests.Session()
    sess.headers.update({"User-Agent": "Mozilla/5.0"})
    try:
        sess.get("https://fc.yahoo.com/", timeout=10)
        crumb = sess.get("https://query2.finance.yahoo.com/v1/test/getcrumb", timeout=10).text.strip()
    except:
        crumb = ""

    ts_end = int(now)
    ts_start = ts_end - 60 * 86400  # 60天足够动量+周线
    all_prices = {}
    for tkr in tickers + ["QQQ", "PSQ"]:
        try:
            url = f"https://query2.finance.yahoo.com/v8/finance/chart/{tkr}?period1={ts_start}&period2={ts_end}&interval=1d&crumb={crumb}"
            r = sess.get(url, timeout=10)
            result = r.json()["chart"]["result"][0]
            adj = result["indicators"]["adjclose"][0]["adjclose"]
            ts_arr = result["timestamp"]
            all_prices[tkr] = {
                datetime.fromtimestamp(ts).strftime("%Y-%m-%d"): p
                for ts, p in zip(ts_arr, adj) if p is not None
            }
            time.sleep(0.25)
        except:
            pass

    cache = {"_ts": now, "data": all_prices}
    with open(PRICE_CACHE, "wb") as f:
        pickle.dump(cache, f)
    return all_prices

def compute_momentum(prices, ticker, recent_dates):
    """20日动量"""
    vals = [prices[ticker].get(d) for d in recent_dates[-LOOKBACK:] if d in prices[ticker] and prices[ticker][d]]
    if len(vals) < 2:
        return None, None
    return round((vals[-1]/vals[0]-1)*100, 1), vals[-1]

def build_report():
    tradable = get_bpx_tradable()
    all_prices = yahoo_prices(tradable)

    # QQQ 日期基准
    qqq_dates = sorted(all_prices.get("QQQ", {}).keys())
    if not qqq_dates:
        return {"error": "数据获取失败"}

    today = qqq_dates[-1]
    last_week = qqq_dates[-5] if len(qqq_dates) >= 5 else qqq_dates[0]
    week_start = qqq_dates[-6] if len(qqq_dates) >= 6 else qqq_dates[0]

    # QQQ / PSQ 本周涨跌
    qqq_now = all_prices["QQQ"].get(today)
    qqq_lw = all_prices["QQQ"].get(last_week)
    psq_now = all_prices.get("PSQ", {}).get(today)
    psq_lw = all_prices.get("PSQ", {}).get(last_week)
    qqq_w = round((qqq_now/qqq_lw-1)*100, 1) if qqq_now and qqq_lw else 0
    psq_w = round((psq_now/psq_lw-1)*100, 1) if psq_now and psq_lw else 0

    # 动量排名（20日 + 5日）
    momentum_list = []
    for tkr in tradable:
        if tkr not in all_prices:
            continue
        mom, price = compute_momentum(all_prices, tkr, qqq_dates)
        if mom is not None and price is not None:
            # 5日动量
            p_wk = all_prices[tkr].get(week_start)
            p_now = all_prices[tkr].get(today)
            mom5 = round((p_now/p_wk-1)*100, 1) if p_wk and p_now and p_wk>0 else None
            momentum_list.append({"symbol": tkr, "momentum": mom, "momentum_5d": mom5, "price": round(price, 2)})

    # 20日排名（用于展示）
    momentum_list.sort(key=lambda x: x["momentum"] or -999, reverse=True)
    for i, m in enumerate(momentum_list):
        m["rank"] = i + 1

    # 方案B选股：20日动量>0 的门槛内，按5日动量排序取Top K
    qualified = [m for m in momentum_list if m["momentum"] > 0 and m["momentum_5d"] is not None]
    qualified.sort(key=lambda x: x["momentum_5d"], reverse=True)
    top_k = qualified[:TOP_K]
    top_k_syms = {m["symbol"] for m in top_k}

    # 对比上周持仓
    try:
        old_data = json.load(open(DATA_FILE)) if os.path.exists(DATA_FILE) else {}
    except:
        old_data = {}
    old_holdings = set(old_data.get("top_symbols", []))
    added = top_k_syms - old_holdings
    removed = old_holdings - top_k_syms
    kept = top_k_syms & old_holdings

    # 策略本周 + 每只持仓股5日动量
    stock_ret = 0
    cnt = 0
    for m in top_k:
        p_wk = all_prices.get(m["symbol"], {}).get(week_start)
        p_now = all_prices.get(m["symbol"], {}).get(today)
        if p_wk and p_now and p_wk > 0:
            m5 = round((p_now / p_wk - 1) * 100, 1)
            stock_ret += m5
            cnt += 1
        else:
            m5 = None
        m["momentum_5d"] = m5
    stock_avg = stock_ret / cnt if cnt > 0 else 0
    strat_w = round(stock_avg * 0.5 + psq_w * 0.5, 1)

    # 全市场5日动量排名（独立于选股）
    week_candidates = [m for m in momentum_list if m["momentum_5d"] is not None]
    week_candidates.sort(key=lambda x: x["momentum_5d"], reverse=True)
    week_top5 = [{"symbol": m["symbol"], "momentum_5d": m["momentum_5d"], "price": m["price"]}
                 for m in week_candidates[:5]]

    # QQQ 近 12 周走势
    qqq_12w = []
    step = max(1, len(qqq_dates)//12)
    for d in qqq_dates[-60::step]:
        qqq_12w.append({"date": d, "qqq": all_prices["QQQ"].get(d), "psq": all_prices.get("PSQ", {}).get(d)})

    # 按动量排名排序，确保顺序与持仓表一致
    rank_order = {m["symbol"]: i for i, m in enumerate(top_k)}
    sorted_added = sorted(added, key=lambda s: rank_order.get(s, 99))
    sorted_kept = sorted(kept, key=lambda s: rank_order.get(s, 99))
    sorted_top_symbols = sorted(top_k_syms, key=lambda s: rank_order.get(s, 99))

    report = {
        "date": today,
        "week_start": week_start,
        "pool_size": len(momentum_list),
        "momentum_top5": top_k,
        "week_top5": week_top5,
        "top_symbols": sorted_top_symbols,
        "changes": {
            "added": [{"symbol": s, "momentum": next((m["momentum"] for m in top_k if m["symbol"]==s),0)} for s in sorted_added],
            "removed": sorted(removed),
            "kept": sorted_kept,
        },
        "performance": {
            "strategy_w": strat_w,
            "qqq_w": qqq_w,
            "psq_w": psq_w,
        },
        "qqq_12w": qqq_12w,
        "full_momentum": momentum_list[:30],
        "backtest": None,
        "all_holdings": [{"symbol": m["symbol"], "momentum": m["momentum"], "momentum_5d": m.get("momentum_5d"), "price": m["price"]} for m in top_k],
    }

    # 缓存
    with open(DATA_FILE, "w") as f:
        json.dump(report, f, ensure_ascii=False, default=str)

    return report

# ==== Routes ====
@app.route("/")
def index():
    with open(TEMPLATE, encoding="utf-8") as f:
        tpl = f.read()
    report = build_report()
    if os.path.exists(BT_FILE):
        with open(BT_FILE, encoding="utf-8") as f:
            report["backtest"] = json.load(f)
    snap = json.dumps(report, ensure_ascii=False)
    html = tpl.replace("__SNAP__", snap)
    return html

@app.route("/api/report")
def api_report():
    r = build_report()
    if os.path.exists(BT_FILE):
        with open(BT_FILE, encoding="utf-8") as f:
            r["backtest"] = json.load(f)
    return jsonify(r)

@app.route("/api/refresh")
def api_refresh():
    if os.path.exists(PRICE_CACHE):
        os.remove(PRICE_CACHE)
    report = build_report()
    return jsonify({"ok": True, "date": report["date"]})

if __name__ == "__main__":
    print(f"NDX动量对冲策略 端口 {PORT}")
    app.run(host="0.0.0.0", port=PORT, threaded=True, debug=False)
