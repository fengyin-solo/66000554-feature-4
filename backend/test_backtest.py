import sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))
from fastapi.testclient import TestClient
from main import app, GridConfig, run_backtest_engine, validate_config

client = TestClient(app)
BASE = dict(lowerPrice=95, upperPrice=115, gridCount=20, capitalPerGrid=1000, initialCapital=100000,
            feeRate=0.03, slippagePct=0.02, minQty=0, gridMode="arithmetic",
            fillCountMode="all", applyScope="future")

fails = []
def check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), name, detail)
    if not cond: fails.append(name)

# 1) 基础回测 + 对账
r = client.post("/api/backtest", json=BASE).json()
recon = round(r["realizedProfit"] + r["floatingProfit"], 2)
check("对账: 已实现+浮动=总盈亏", recon == r["totalProfit"], f"{recon} vs {r['totalProfit']}")
final_equity = round(r["finalCash"] + r["finalHoldings"] * r["finalPrice"], 2)
check("对账: 末点净值=初始+总盈亏",
      final_equity == round(100000 + r["totalProfit"], 2) == round(r["equityCurve"][-1], 2),
      f"{final_equity} / {r['equityCurve'][-1]}")
check("成交笔数(全部)=买+卖", r["fillCount"] == r["buyCount"] + r["sellCount"], str(r["fillCount"]))
filled_sells = [o for o in r["orders"] if o["side"]=="SELL" and o["status"]=="FILLED"]
check("卖出笔数一致", len(filled_sells) == r["sellCount"])
sum_profit = round(sum(o["profit"] for o in filled_sells), 2)
check("卖出盈亏合计=已实现盈亏", sum_profit == r["realizedProfit"], f"{sum_profit} vs {r['realizedProfit']}")
check("报告回传口径", r["params"]["feeRate"]==0.03 and r["params"]["gridMode"]=="arithmetic")
check("净值序列长度=价格数+1", len(r["equityCurve"]) == 202)

# 2) 确定性：同样的输入必须逐位一致（保证"同时重算已有报告"可复现）
r2 = client.post("/api/backtest", json=BASE).json()
check("相同口径结果完全一致", r2 == r)

# 3) 手续费率提高 -> 总盈亏不增
hi_fee = {**BASE, "feeRate": 0.5}
r3 = client.post("/api/backtest", json=hi_fee).json()
check("手续费提高利润下降", r3["totalProfit"] < r["totalProfit"], f"{r3['totalProfit']} vs {r['totalProfit']}")
check("费率改变后收益率同向", r3["returnRate"] < r["returnRate"])
# 夏普/回撤也都来自新净值（存在重算）
check("高费率净值不同", r3["equityCurve"] != r["equityCurve"])

# 4) 滑点为零 vs 有滑点
r4 = client.post("/api/backtest", json={**BASE, "slippagePct": 0, "feeRate": 0}).json()
r4b = client.post("/api/backtest", json={**BASE, "slippagePct": 1, "feeRate": 0}).json()
check("滑点增大利润下降", r4b["totalProfit"] < r4["totalProfit"], f"{r4b['totalProfit']} vs {r4['totalProfit']}")

# 5) 单笔最小成交量：设极大值 -> 全部买入拒单，零成交
r5 = client.post("/api/backtest", json={**BASE, "minQty": 1e6}).json()
check("最小量过大->无成交", r5["buyCount"]==0 and r5["sellCount"]==0 and r5["fillCount"]==0)
check("拒单有原因标记", r5["rejectedCount"]>0 and all(o.get("reason") for o in r5["orders"] if o["status"]=="REJECTED"))
check("无成交时指标为0", r5["totalProfit"]==0 and r5["returnRate"]==0 and r5["maxDrawdown"]==0 and r5["winRate"]==0)
check("拒单不计入任何口径", r5["fillCount"]==0)

# 6) 成交笔数口径
cfg_sell = {**BASE, "fillCountMode": "sell"}
cfg_buy = {**BASE, "fillCountMode": "buy"}
cfg_round = {**BASE, "fillCountMode": "round"}
rs = client.post("/api/backtest", json=cfg_sell).json()
rb = client.post("/api/backtest", json=cfg_buy).json()
rr = client.post("/api/backtest", json=cfg_round).json()
check("笔数口径-卖出", rs["fillCount"]==rs["sellCount"])
check("笔数口径-买入", rb["fillCount"]==rb["buyCount"])
check("笔数口径-回合=卖出", rr["fillCount"]==rr["sellCount"])
check("口径不影响盈亏", rs["totalProfit"]==r["totalProfit"] and rb["totalProfit"]==r["totalProfit"])

# 7) 等比网格
rg = client.post("/api/backtest", json={**BASE, "gridMode": "geometric"}).json()
check("等比网格可运行且有成交", rg["buyCount"]+rg["sellCount"]>0)
check("等比间距文本", rg["params"]["spacingText"].endswith("（等比）"), rg["params"]["spacingText"])
check("等比网格同样可对账", round(rg["realizedProfit"]+rg["floatingProfit"],2)==rg["totalProfit"])

# 8) 校验：填反 / 越界 / 为空 / 非法枚举
def bad(payload, *fields):
    resp = client.post("/api/backtest", json=payload)
    ok_status = resp.status_code == 400
    got = {d["field"] for d in resp.json()["detail"]}
    ok_fields = set(fields) <= got
    check(f"校验拒绝[{','.join(fields)}]", ok_status and ok_fields, f"status={resp.status_code} got={got}")

bad({**BASE, "upperPrice": 90}, "upperPrice")
bad({**BASE, "upperPrice": 95}, "upperPrice")
bad({**BASE, "feeRate": -0.01}, "feeRate")
bad({**BASE, "feeRate": 1.01}, "feeRate")
bad({**BASE, "slippagePct": 5.01}, "slippagePct")
bad({**BASE, "minQty": -1}, "minQty")
bad({**BASE, "gridCount": 0}, "gridCount")
bad({**BASE, "gridCount": 2.5}, "gridCount")
bad({**BASE, "lowerPrice": None, "feeRate": None}, "lowerPrice", "feeRate")
bad({**BASE, "gridMode": "magic"}, "gridMode")
bad({**BASE, "fillCountMode": "weird"}, "fillCountMode")
bad({**BASE, "applyScope": "now"}, "applyScope")
resp = client.post("/api/backtest", json={**BASE, "lowerPrice": -5, "feeRate": 9, "slippagePct": None})
check("多项不合格一次性指出", resp.status_code==400 and len(resp.json()["detail"])==3, str(resp.json().get("detail")))

# 9) 合法边界值
edge = {**BASE, "feeRate": 0, "slippagePct": 0, "minQty": 0}
check("零费率/零滑点/零最小量通过", client.post("/api/backtest", json=edge).status_code==200)
edge2 = {**BASE, "feeRate": 1, "slippagePct": 5}
check("上界值通过", client.post("/api/backtest", json=edge2).status_code==200)

# 10) 胜率
wins = sum(1 for o in filled_sells if o["profit"]>0)
check("胜率对账", (round(wins/len(filled_sells)*100,1) if filled_sells else 0)==r["winRate"])

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)
