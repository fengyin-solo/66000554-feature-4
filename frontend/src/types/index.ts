export interface Tick { time: string; price: number; bid: number; ask: number; volume: number }
export interface OrderBook { bids: [number,number][]; asks: [number,number][]; midPrice: number; spread: number }

export type GridMode = 'arithmetic' | 'geometric'
export type FillCountMode = 'all' | 'buy' | 'sell' | 'round'
export type ApplyScope = 'future' | 'recompute'

export interface BacktestParams {
  feeRate: number        // 手续费率 %
  slippagePct: number    // 滑点 %
  minQty: number         // 单笔最小成交量
  gridMode: GridMode     // 网格间距口径
  fillCountMode: FillCountMode // 成交笔数口径
  applyScope: ApplyScope       // 保存后生效方式
}

export interface GridConfig extends BacktestParams {
  lowerPrice: number
  upperPrice: number
  gridCount: number
  capitalPerGrid: number
  initialCapital: number
}

export interface ReportParams {
  feeRate: number
  slippagePct: number
  minQty: number
  gridMode: GridMode
  gridModeLabel: string
  fillCountMode: FillCountMode
  fillCountModeLabel: string
  spacingText: string
  lowerPrice: number
  upperPrice: number
  gridCount: number
  capitalPerGrid: number
  initialCapital: number
}

export interface GridOrder { id: number; price: number; side: string; quantity: number; status: string; profit: number; fee?: number; reason?: string }
export interface GridResult {
  orders: GridOrder[]
  totalProfit: number
  returnRate: number
  sharpeRatio: number
  maxDrawdown: number
  winRate: number
  equityCurve: number[]
  fillCount: number
  buyCount: number
  sellCount: number
  rejectedCount: number
  realizedProfit: number
  floatingProfit: number
  finalCash: number
  finalHoldings: number
  finalPrice: number
  params: ReportParams
}

export interface FieldError { field: string; message: string }
