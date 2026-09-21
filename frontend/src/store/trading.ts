import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'
import type { Tick, OrderBook, GridConfig, GridResult, CaliberErrors, ApplyMode } from '@/types'

export const DEFAULT_STRATEGY = 'default'

const DEFAULT_CONFIG: GridConfig = {
  strategyId: DEFAULT_STRATEGY,
  lowerPrice: 95,
  upperPrice: 115,
  gridCount: 20,
  gridSpacing: 1,
  spacingMode: 'count',
  capitalPerGrid: 1000,
  initialCapital: 100000,
  caliber: { feeRate: 0.0003, slippagePct: 0.001, minQuantity: 1 },
  tradeCountMode: 'roundtrip'
}

const configKey = (id: string) => `gte:config:${id}`
const applyModeKey = (id: string) => `gte:applyMode:${id}`

function loadConfig(): GridConfig {
  try {
    const raw = localStorage.getItem(configKey(DEFAULT_STRATEGY))
    if (raw) return { ...DEFAULT_CONFIG, ...JSON.parse(raw), caliber: { ...DEFAULT_CONFIG.caliber, ...(JSON.parse(raw).caliber || {}) } }
  } catch {}
  return { ...DEFAULT_CONFIG, caliber: { ...DEFAULT_CONFIG.caliber } }
}

function loadApplyMode(): ApplyMode {
  return localStorage.getItem(applyModeKey(DEFAULT_STRATEGY)) === 'recompute' ? 'recompute' : 'future'
}

export const useTradingStore = defineStore('trading', () => {
  const loading = ref(false)
  const ticks = ref<Tick[]>([])
  const orderBook = ref<OrderBook | null>(null)
  const gridResult = ref<GridResult | null>(null)
  const wsConnected = ref(false)
  const config = ref<GridConfig>(loadConfig())
  // 保存口径时选择的生效方式：刷新后沿用上次选择
  const applyMode = ref<ApplyMode>(loadApplyMode())
  // 最近一次校验的不合格项（字段名 -> 原因），供表单逐项标错
  const caliberErrors = ref<CaliberErrors>({})

  let ws: WebSocket | null = null
  function connectWS() {
    ws = new WebSocket(`ws://${location.hostname}:8000/ws`)
    ws.onopen = () => { wsConnected.value = true }
    ws.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data)
        if (d.ticks) ticks.value = d.ticks.slice(-60)
        if (d.orderBook) orderBook.value = d.orderBook
      } catch {}
    }
    ws.onclose = () => { wsConnected.value = false }
  }

  function persistConfig() {
    localStorage.setItem(configKey(config.value.strategyId), JSON.stringify(config.value))
  }

  function setApplyMode(mode: ApplyMode) {
    applyMode.value = mode
    localStorage.setItem(applyModeKey(config.value.strategyId), mode)
  }

  /** 调用后端逐字段校验；不合格时写入 caliberErrors 并返回 false（空值/越界/填反均不通过） */
  async function validateCaliber(): Promise<boolean> {
    try {
      await axios.post('/api/backtest', { ...config.value, validateOnly: true })
      caliberErrors.value = {}
      return true
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      caliberErrors.value = detail?.code === 'invalid_caliber' ? detail.errors : {}
      return false
    }
  }

  /** 用当前配置跑一次回测；返回是否成功 */
  async function runBacktest(): Promise<boolean> {
    if (!(await validateCaliber())) return false
    loading.value = true
    try {
      const { data } = await axios.post('/api/backtest', config.value)
      gridResult.value = data
      persistConfig()
      return true
    } finally {
      loading.value = false
    }
  }

  /**
   * 保存回测口径：校验通过后才允许保存（持久化，刷新沿用）。
   * applyMode='recompute' 且已有报告时，用新口径同时重算已有报告；
   * 'future' 则只对后续回测生效，已有报告保留原口径快照。
   */
  async function saveCaliber(): Promise<boolean> {
    if (!(await validateCaliber())) return false
    persistConfig()
    if (applyMode.value === 'recompute' && gridResult.value) {
      return runBacktest()
    }
    return true
  }

  function disconnectWS() { ws?.close(); ws = null; wsConnected.value = false }

  return {
    loading, ticks, orderBook, gridResult, wsConnected, config,
    applyMode, caliberErrors,
    connectWS, runBacktest, saveCaliber, validateCaliber, setApplyMode, disconnectWS
  }
})
