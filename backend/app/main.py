import asyncio, time, random, math, json, threading
from typing import Optional, List, Tuple
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Grid Trading Engine")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

ACTIVE_CLIENTS = []
SIM_RUNNING = True
current_price = 100.0
ticks_history = []

GRID_MODES = {"arithmetic": "等差网格", "geometric": "等比网格"}
FILL_COUNT_MODES = {"all": "全部成交", "buy": "仅买入", "sell": "仅卖出", "round": "完整回合"}
APPLY_SCOPES = {"future": "仅对后续回测生效", "recompute": "同时重算已有报告"}


class GridConfig(BaseModel):
    lowerPrice: Optional[float] = 95
    upperPrice: Optional[float] = 115
    gridCount: Optional[float] = 20  # 数字进入后由 validate_config 校验整数，保证错误格式统一
    capitalPerGrid: Optional[float] = 1000
    initialCapital: Optional[float] = 100000
    # 可编辑的回测口径（按策略分别调整）
    feeRate: Optional[float] = 0.03        # 手续费率，单位 %（按成交金额单边收取）
    slippagePct: Optional[float] = 0.02    # 滑点，单位 %（买入价上抬/卖出价下压）
    minQty: Optional[float] = 0            # 单笔最小成交量
    gridMode: Optional[str] = "arithmetic"          # 网格间距口径：等差 / 等比
    fillCountMode: Optional[str] = "all"            # 成交笔数口径：全部/买入/卖出/完整回合
    applyScope: Optional[str] = "future"            # 保存后：仅后续生效 / 同时重算已有报告


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))


def validate_config(c: GridConfig) -> List[Tuple[str, str]]:
    """返回不合格项 [(field, message), ...]，为空时表示全部合格。"""
    errs: List[Tuple[str, str]] = []

    def check_number(field: str, label: str, v, lo: float, hi: float, integer=False):
        if v is None:
            errs.append((field, f"{label}不能为空"))
        elif not _is_number(v):
            errs.append((field, f"{label}必须为有效数字"))
        elif integer and float(v) != int(float(v)):
            errs.append((field, f"{label}必须为整数"))
        elif v < lo or v > hi:
            errs.append((field, f"{label}超出允许范围（{lo:g} ~ {hi:g}）"))

    check_number("lowerPrice", "下限价格", c.lowerPrice, 0.01, 100000)
    check_number("upperPrice", "上限价格", c.upperPrice, 0.01, 100000)
    if _is_number(c.lowerPrice) and _is_number(c.upperPrice) and c.upperPrice <= c.lowerPrice:
        errs.append(("upperPrice", "上限价格必须大于下限价格"))
    check_number("gridCount", "网格数量", c.gridCount, 1, 500, integer=True)
    check_number("capitalPerGrid", "每格资金", c.capitalPerGrid, 0.01, 1e12)
    check_number("initialCapital", "初始资金", c.initialCapital, 1, 1e12)
    check_number("feeRate", "手续费率(%)", c.feeRate, 0, 1)
    check_number("slippagePct", "滑点(%)", c.slippagePct, 0, 5)
    check_number("minQty", "单笔最小成交量", c.minQty, 0, 1e9)
    if c.gridMode not in GRID_MODES:
        errs.append(("gridMode", "网格间距口径无效"))
    if c.fillCountMode not in FILL_COUNT_MODES:
        errs.append(("fillCountMode", "成交笔数口径无效"))
    if c.applyScope not in APPLY_SCOPES:
        errs.append(("applyScope", "生效方式无效"))
    return errs


def simulate_market():
    global current_price, ticks_history
    price = 100.0
    while SIM_RUNNING:
        drift = 0.005 * math.sin(time.time() * 0.05)
        price += random.gauss(drift, 0.3)
        price = max(80, min(130, price))
        current_price = price
        tick = {
            "time": time.strftime("%H:%M:%S"),
            "price": round(price, 2),
            "bid": round(price - random.uniform(0.01, 0.05), 2),
            "ask": round(price + random.uniform(0.01, 0.05), 2),
            "volume": random.randint(100, 5000)
        }
        ticks_history.append(tick)
        if len(ticks_history) > 200:
            ticks_history = ticks_history[-200:]

        # Order book
        bids = [[round(price - 0.01 * i, 2), random.randint(100, 1000)] for i in range(1, 11)]
        asks = [[round(price + 0.01 * i, 2), random.randint(100, 1000)] for i in range(1, 11)]
        order_book = {"bids": bids, "asks": asks, "midPrice": price, "spread": round(asks[0][0] - bids[0][0], 2)}

        payload = json.dumps({"ticks": ticks_history[-60:], "orderBook": order_book})
        for ws in ACTIVE_CLIENTS:
            try: asyncio.run_coroutine_threadsafe(ws.send_text(payload), asyncio.get_event_loop())
            except: pass
        time.sleep(0.5)


@app.on_event("startup")
async def startup():
    threading.Thread(target=simulate_market, daemon=True).start()


def run_backtest_engine(config: GridConfig) -> dict:
    """按给定口径执行回测。价格路径使用固定种子，保证口径调整后可在同一份数据上重算。"""
    fee_rate = config.feeRate / 100.0
    slip = config.slippagePct / 100.0

    # 网格价位：间距口径决定等差还是等比
    n = int(config.gridCount)
    if config.gridMode == "geometric":
        ratio = (config.upperPrice / config.lowerPrice) ** (1.0 / n)
        grid_prices = [config.lowerPrice * ratio ** i for i in range(n + 1)]

        def sell_target(gp: float) -> float:
            return gp * ratio ** 0.5

        spacing_text = f"{(ratio - 1) * 100:.3f}%（等比）"
    else:
        step = (config.upperPrice - config.lowerPrice) / n
        grid_prices = [config.lowerPrice + i * step for i in range(n + 1)]

        def sell_target(gp: float) -> float:
            return gp + step * 0.5

        spacing_text = f"{step:.4f}（等差）"

    # 固定价格路径：相同策略参数重算结果可复现，仅口径变化会改变结果
    rng = random.Random(42)
    prices = [100.0]
    for _ in range(200):
        prices.append(prices[-1] + rng.gauss(0, 1.2))
    prices = [max(70.0, min(140.0, p)) for p in prices]

    open_grids = {}        # 网格价 -> {"qty": 持仓量, "cost": 含费买入入账成本（分精度）}
    orders = []
    cash = config.initialCapital
    holdings = 0.0
    equity_curve = [round(cash, 2)]
    order_id = 0
    realized_profit = 0.0
    rejected_count = 0
    buy_count = 0
    sell_count = 0

    def append_order(**kw):
        nonlocal order_id
        order_id += 1
        orders.append({"id": order_id, **kw})

    for p in prices:
        for gp in grid_prices:
            # ---- 买入信号 ----
            if p <= gp and gp not in open_grids:
                qty = config.capitalPerGrid / gp
                fill_price = gp * (1 + slip)                 # 滑点：买单向上成交
                fee = round(qty * fill_price * fee_rate, 2)
                cost = round(qty * fill_price + fee, 2)      # 入账成本（含费、分精度）
                if qty < config.minQty:
                    rejected_count += 1
                    append_order(price=round(gp, 2), side="BUY", quantity=round(qty, 2),
                                 status="REJECTED", profit=0, fee=0, reason="低于单笔最小成交量")
                elif cash < cost:
                    rejected_count += 1
                    append_order(price=round(gp, 2), side="BUY", quantity=round(qty, 2),
                                 status="REJECTED", profit=0, fee=0, reason="可用资金不足")
                else:
                    cash = round(cash - cost, 2)
                    holdings += qty
                    open_grids[gp] = {"qty": qty, "cost": cost}
                    buy_count += 1
                    append_order(price=round(fill_price, 2), side="BUY", quantity=round(qty, 2),
                                 status="FILLED", profit=0, fee=fee)

            # ---- 卖出信号（与买入共用同一份间距口径）----
            target = sell_target(gp)
            if p >= target and gp in open_grids:
                lot = open_grids.pop(gp)
                qty = lot["qty"]
                fill_price = target * (1 - slip)             # 滑点：卖单向下成交
                fee = round(qty * fill_price * fee_rate, 2)
                proceeds = round(qty * fill_price - fee, 2)
                profit = round(proceeds - lot["cost"], 2)    # 单笔盈亏含双边手续费
                cash = round(cash + proceeds, 2)
                holdings -= qty
                realized_profit = round(realized_profit + profit, 2)
                sell_count += 1
                append_order(price=round(fill_price, 2), side="SELL", quantity=round(qty, 2),
                             status="FILLED", profit=profit, fee=fee)

        equity_curve.append(round(cash + holdings * p, 2))

    last_price = prices[-1]
    # 总盈亏以账户终值为准；浮动盈亏反推，保证「已实现+浮动=总盈亏=末点净值-初始资金」对得上
    total_profit = round(cash + holdings * last_price - config.initialCapital, 2)
    floating_profit = round(total_profit - realized_profit, 2)
    return_rate = total_profit / config.initialCapital * 100

    # 夏普比率
    eq_returns = np.diff(equity_curve) / (np.array(equity_curve[:-1], dtype=float) + 1e-5)
    sharpe = float(np.mean(eq_returns) / max(np.std(eq_returns), 1e-5) * np.sqrt(252)) if len(eq_returns) > 1 else 0.0

    # 最大回撤
    peak = equity_curve[0]
    max_dd = 0.0
    for e in equity_curve:
        if e > peak:
            peak = e
        dd = (peak - e) / peak * 100 if peak > 0 else 0.0
        max_dd = max(max_dd, dd)

    wins = sum(1 for o in orders if o["side"] == "SELL" and o["status"] == "FILLED" and o["profit"] > 0)
    win_rate = (wins / sell_count * 100) if sell_count > 0 else 0.0

    # 成交笔数按所选口径统计（仅统计真实成交，拒单不计入任何口径）
    fill_count = {"all": buy_count + sell_count, "buy": buy_count,
                  "sell": sell_count, "round": sell_count}[config.fillCountMode]

    return {
        "orders": orders,
        "totalProfit": round(total_profit, 2),
        "returnRate": round(return_rate, 2),
        "sharpeRatio": round(sharpe, 2),
        "maxDrawdown": round(max_dd, 2),
        "winRate": round(win_rate, 1),
        "equityCurve": equity_curve,
        # 成交明细与绩效指标的对账字段
        "fillCount": fill_count,
        "buyCount": buy_count,
        "sellCount": sell_count,
        "rejectedCount": rejected_count,
        "realizedProfit": round(realized_profit, 2),
        "floatingProfit": round(floating_profit, 2),
        "finalCash": round(cash, 2),
        "finalHoldings": round(holdings, 6),
        "finalPrice": round(last_price, 2),
        # 本份报告实际使用的口径（前端据此展示并校验一致性）
        "params": {
            "feeRate": config.feeRate,
            "slippagePct": config.slippagePct,
            "minQty": config.minQty,
            "gridMode": config.gridMode,
            "gridModeLabel": GRID_MODES[config.gridMode],
            "fillCountMode": config.fillCountMode,
            "fillCountModeLabel": FILL_COUNT_MODES[config.fillCountMode],
            "spacingText": spacing_text,
            "lowerPrice": config.lowerPrice,
            "upperPrice": config.upperPrice,
            "gridCount": n,
            "capitalPerGrid": config.capitalPerGrid,
            "initialCapital": config.initialCapital,
        }
    }


@app.post("/api/backtest")
def run_backtest(config: GridConfig):
    errs = validate_config(config)
    if errs:
        raise HTTPException(status_code=400, detail=[{"field": f, "message": m} for f, m in errs])
    return run_backtest_engine(config)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    ACTIVE_CLIENTS.append(ws)
    try:
        while True: await ws.receive_text()
    except:
        if ws in ACTIVE_CLIENTS: ACTIVE_CLIENTS.remove(ws)
