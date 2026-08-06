# -*- coding: utf-8 -*-
"""生成静态 HTML 快照（GitHub Pages 部署用）"""
import server, json, os

report = server.build_report()
# 加载回测
BT_FILE = os.path.join(os.path.dirname(__file__), "backtest_5y.json")
if os.path.exists(BT_FILE):
    report["backtest"] = json.load(open(BT_FILE, encoding="utf-8"))

snap = json.dumps(report, ensure_ascii=False)

with open("templates/dashboard.html", encoding="utf-8") as f:
    tpl = f.read()

html = tpl.replace("__SNAP__", snap)

os.makedirs("docs", exist_ok=True)
with open("docs/index.html", "w", encoding="utf-8") as f:
    f.write(html)

print(f"生成 docs/index.html ({len(html)} bytes)")
