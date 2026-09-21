import asyncio, time, random, math, json, threading
from typing import Optional
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

# ---- 回测口径（可按策略分别调整）----
SPACING_MODES = {"count", "spacing"}                       # 网格间距口径：按网格数量 / 按网格间距
TRADE_COUNT_MODES = {"all", "filled", "roundtrip"}        # 成交笔数口径：全部委托 / 仅成交 / 完整买卖对
FEE_RATE_MAX = 0.01        # 手续费率上限 1%
SLIPPAGE_PCT_MAX = 0.02    # 滑点上限 2%
MIN_QUANTITY_MAX = 100000  # 单笔最小成交量上限
GRID_COUNT_MIN, GRID_COUNT_MAX = 2, 500


class BacktestCaliber(BaseModel):
    feeRate: Optional[float] = None          # 手续费率（按成交额，双边收取），如 0.0003 = 万三
    slippagePct: Optional[float] = None      # 滑点（占成交价比例），如 0.001 = 0.1%
    minQuantity: Optional[float] = None      # 单笔最小成交量，低于该值拒单


class GridConfig(BaseModel):
    strategyId: str = "default"
    lowerPrice: Optional[float] = None
    upperPrice: Optional[float] = None
    gridCount: Optional[int] = None
    gridSpacing: Optional[float] = None
    spacingMode: str = "count"
    capitalPerGrid: Optional[float] = None
    initialCapital: Optional[float] = None
    caliber: Optional[BacktestCaliber] = None
    tradeCountMode: str = "roundtrip"
    validateOnly: bool = False


def _finite(v) -> bool:
    return v is not None and isinstance(v, (int, float)) and math.isfinite(v)


def validate_config(c: GridConfig) -> dict:
    """逐字段校验回测配置与口径，返回 {字段: 不合格原因}；为空表示全部合格。"""
    errors = {}

    if not _finite(c.lowerPrice) or c.lowerPrice <= 0:
        errors["lowerPrice"] = "下限价格必须为大于 0 的数值"
    if not _finite(c.upperPrice) or c.upperPrice <= 0:
        errors["upperPrice"] = "上限价格必须为大于 0 的数值"
    if "lowerPrice" not in errors and "upperPrice" not in errors and c.upperPrice <= c.lowerPrice:
        errors["upperPrice"] = "上限价格必须大于下限价格（区间不能填反）"

    if c.spacingMode not in SPACING_MODES:
        errors["spacingMode"] = "网格间距口径只能为「按网格数量」或「按网格间距」"

    price_range = (c.upperPrice - c.lowerPrice) if _finite(c.upperPrice) and _finite(c.lowerPrice) else 0
    if c.spacingMode == "count":
        if c.gridCount is None:
            errors["gridCount"] = "网格数量不能为空"
        elif not isinstance(c.gridCount, int) or c.gridCount < GRID_COUNT_MIN or c.gridCount > GRID_COUNT_MAX:
            errors["gridCount"] = f"网格数量需为 {GRID_COUNT_MIN}~{GRID_COUNT_MAX} 之间的整数"
    else:
        if not _finite(c.gridSpacing):
            errors["gridSpacing"] = "网格间距不能为空"
        elif c.gridSpacing <= 0:
            errors["gridSpacing"] = "网格间距必须大于 0"
        elif price_range > 0 and c.gridSpacing >= price_range:
            errors["gridSpacing"] = "网格间距必须小于价格区间宽度（上限-下限）"
    if not _finite(c.capitalPerGrid) or c.capitalPerGrid <= 0:
        errors["capitalPerGrid"] = "每格资金必须大于 0"
    if not _finite(c.initialCapital) or c.initialCapital <= 0:
        errors["initialCapital"] = "初始资金必须大于 0"

    cal = c.caliber
    if cal is None:
        errors["caliber"] = "回测口径不能为空（手续费率/滑点/单笔最小成交量）"
    else:
        if not _finite(cal.feeRate):
            errors["caliber.feeRate"] = "手续费率不能为空"
        elif cal.feeRate < 0 or cal.feeRate > FEE_RATE_MAX:
            errors["caliber.feeRate"] = f"手续费率需在 0~{FEE_RATE_MAX * 100:g}% 之间"
        if not _finite(cal.slippagePct):
            errors["caliber.slippagePct"] = "滑点不能为空"
        elif cal.slippagePct < 0 or cal.slippagePct > SLIPPAGE_PCT_MAX:
            errors["caliber.slippagePct"] = f"滑点需在 0~{SLIPPAGE_PCT_MAX * 100:g}% 之间"
        if not _finite(cal.minQuantity):
            errors["caliber.minQuantity"] = "单笔最小成交量不能为空"
        elif cal.minQuantity <= 0 or cal.minQuantity > MIN_QUANTITY_MAX:
            errors["caliber.minQuantity"] = f"单笔最小成交量需在 0~{MIN_QUANTITY_MAX:g} 之间"

    if c.tradeCountMode not in TRADE_COUNT_MODES:
        errors["tradeCountMode"] = "成交笔数口径不合法"

    return errors


def resolve_grids(c: GridConfig):
    """按间距口径解析网格线，返回 (grid_prices, step, count)。"""
    if c.spacingMode == "spacing":
        step = float(c.gridSpacing)
        n = max(1, int((c.upperPrice - c.lowerPrice) / step))
        grid_prices = [c.lowerPrice + i * step for i in range(n + 1)]
        return grid_prices, step, n
    step = (c.upperPrice - c.lowerPrice) / c.gridCount
    grid_prices = [c.lowerPrice + i * step for i in range(c.gridCount + 1)]
    return grid_prices, step, c.gridCount


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


@app.post("/api/backtest")
def run_backtest(config: GridConfig):
    errors = validate_config(config)
    if errors:
        # 不合格项逐字段返回，前端据此标记并阻止保存
        raise HTTPException(status_code=400, detail={"code": "invalid_caliber", "errors": errors})
    if config.validateOnly:
        return {"valid": True}

    grid_prices, step, grid_count = resolve_grids(config)
    cal = config.caliber
    fee_rate, slip_pct, min_qty = cal.feeRate, cal.slippagePct, cal.minQuantity

    # 固定随机源的行情：同一份配置/口径重算结果可复现
    rng = np.random.default_rng(42)
    prices = [100.0]
    for _ in range(200):
        prices.append(prices[-1] + float(rng.normal(0, 1.2)))
    prices = [max(70, min(140, p)) for p in prices]

    open_grids = {}    # 网格买入价 -> (持仓数量, 含买入手续费的成本)
    rejected = set()   # 已因低于单笔最小成交量拒单的网格
    orders = []
    cash = config.initialCapital
    holdings = 0.0
    equity_curve = [cash]
    order_id = 0
    total_fees = 0.0

    for p in prices:
        for gp in grid_prices:
            # ---- 买入信号：成交价加滑点，收取买入手续费，校验单笔最小成交量 ----
            if p <= gp and gp not in open_grids and gp not in rejected:
                qty = config.capitalPerGrid / gp
                if qty < min_qty:
                    rejected.add(gp)
                    order_id += 1
                    orders.append({"id": order_id, "price": round(gp, 4), "side": "BUY",
                                   "quantity": round(qty, 4), "status": "REJECTED", "profit": 0.0,
                                   "fee": 0.0, "reason": "低于单笔最小成交量"})
                    continue
                buy_price = gp * (1 + slip_pct)
                fee = buy_price * qty * fee_rate
                cost = buy_price * qty + fee
                if cash < cost:
                    continue  # 资金暂时不足，后续行情仍可再次触发
                cash -= cost
                holdings += qty
                total_fees += fee
                open_grids[gp] = (qty, cost)
                order_id += 1
                orders.append({"id": order_id, "price": round(buy_price, 4), "side": "BUY",
                               "quantity": round(qty, 4), "status": "FILLED", "profit": 0.0,
                               "fee": round(fee, 4), "reason": None})

            # ---- 卖出信号：成交价减滑点，收取卖出手续费，盈亏按含费成本结算 ----
            target = gp + step * 0.5
            if p >= target and gp in open_grids:
                qty, buy_cost = open_grids.pop(gp)
                sell_price = target * (1 - slip_pct)
                fee = sell_price * qty * fee_rate
                net = sell_price * qty - fee
                profit = net - buy_cost
                cash += net
                holdings -= qty
                total_fees += fee
                order_id += 1
                orders.append({"id": order_id, "price": round(sell_price, 4), "side": "SELL",
                               "quantity": round(qty, 4), "status": "FILLED",
                               "profit": round(profit, 4), "fee": round(fee, 4), "reason": None})

        equity_curve.append(round(cash + holdings * p, 2))

    # ---- 绩效指标：全部基于上面同一口径下的资金/成交记录重算 ----
    total_profit = cash + holdings * prices[-1] - config.initialCapital
    return_rate = (total_profit / config.initialCapital) * 100

    eq_returns = np.diff(equity_curve) / (np.array(equity_curve[:-1]) + 1e-5)
    sharpe = float(np.mean(eq_returns) / max(np.std(eq_returns), 1e-5) * np.sqrt(252)) if len(eq_returns) > 1 else 0

    peak = equity_curve[0]
    max_dd = 0.0
    for e in equity_curve:
        if e > peak:
            peak = e
        dd = (peak - e) / peak * 100
        max_dd = max(max_dd, dd)

    sell_orders = [o for o in orders if o["side"] == "SELL" and o["status"] == "FILLED"]
    wins = sum(1 for o in sell_orders if o["profit"] > 0)
    win_rate = (wins / len(sell_orders) * 100) if sell_orders else 0

    if config.tradeCountMode == "all":
        trade_count = len(orders)
    elif config.tradeCountMode == "filled":
        trade_count = sum(1 for o in orders if o["status"] == "FILLED")
    else:  # roundtrip：一笔卖出对应一笔完整买卖
        trade_count = len(sell_orders)

    return {
        "strategyId": config.strategyId,
        "caliber": {"feeRate": fee_rate, "slippagePct": slip_pct, "minQuantity": min_qty},
        "spacingMode": config.spacingMode,
        "gridSpacing": round(step, 4),
        "gridCount": grid_count,
        "tradeCountMode": config.tradeCountMode,
        "tradeCount": trade_count,
        "orders": orders,
        "totalProfit": round(total_profit, 2),
        "returnRate": round(return_rate, 2),
        "sharpeRatio": round(sharpe, 2),
        "maxDrawdown": round(max_dd, 2),
        "winRate": round(win_rate, 1),
        "totalFees": round(total_fees, 2),
        "equityCurve": equity_curve
    }


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    ACTIVE_CLIENTS.append(ws)
    try:
        while True: await ws.receive_text()
    except:
        if ws in ACTIVE_CLIENTS: ACTIVE_CLIENTS.remove(ws)
