export interface Tick { time: string; price: number; bid: number; ask: number; volume: number }
export interface OrderBook { bids: [number,number][]; asks: [number,number][]; midPrice: number; spread: number }

/** 网格间距口径：count=按网格数量推导间距；spacing=直接指定间距推导数量 */
export type SpacingMode = 'count' | 'spacing'
/** 成交笔数口径：all=全部委托（含拒单）；filled=仅成交；roundtrip=完整买卖对 */
export type TradeCountMode = 'all' | 'filled' | 'roundtrip'
/** 口径保存后的生效方式：future=只对后续回测生效；recompute=同时重算已有报告 */
export type ApplyMode = 'future' | 'recompute'

/** 回测口径：可按策略分别调整 */
export interface BacktestCaliber {
  feeRate: number       // 手续费率（双边，按成交额）
  slippagePct: number   // 滑点（占成交价比例）
  minQuantity: number   // 单笔最小成交量
}

export interface GridConfig {
  strategyId: string
  lowerPrice: number
  upperPrice: number
  gridCount: number
  gridSpacing: number
  spacingMode: SpacingMode
  capitalPerGrid: number
  initialCapital: number
  caliber: BacktestCaliber
  tradeCountMode: TradeCountMode
}

export interface GridOrder {
  id: number
  price: number
  side: string
  quantity: number
  status: string        // FILLED / REJECTED
  profit: number
  fee: number
  reason: string | null
}

export interface GridResult {
  strategyId: string
  caliber: BacktestCaliber
  spacingMode: SpacingMode
  gridSpacing: number
  gridCount: number
  tradeCountMode: TradeCountMode
  tradeCount: number
  orders: GridOrder[]
  totalProfit: number
  returnRate: number
  sharpeRatio: number
  maxDrawdown: number
  winRate: number
  totalFees: number
  equityCurve: number[]
}

/** 后端逐字段校验返回的不合格项：字段名 -> 原因 */
export type CaliberErrors = Record<string, string>
