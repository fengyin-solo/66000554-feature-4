import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'
import { ElMessage } from 'element-plus'
import type { Tick, OrderBook, GridConfig, GridResult, FieldError } from '@/types'
import { validateConfig } from '@/lib/backtestRules'

const CONFIG_KEY = 'grid:config'
const SCOPE_KEY = 'grid:applyScope'
const REPORT_KEY = 'grid:lastReport'

function defaultConfig(): GridConfig {
  return {
    lowerPrice: 95, upperPrice: 115, gridCount: 20, capitalPerGrid: 1000, initialCapital: 100000,
    feeRate: 0.03, slippagePct: 0.02, minQty: 0,
    gridMode: 'arithmetic', fillCountMode: 'all', applyScope: 'future'
  }
}

function loadConfig(): GridConfig {
  try {
    const raw = localStorage.getItem(CONFIG_KEY)
    if (raw) return { ...defaultConfig(), ...JSON.parse(raw) }
  } catch { /* 损坏的缓存不影响启动 */ }
  return defaultConfig()
}

function loadScope(): GridConfig['applyScope'] {
  const v = localStorage.getItem(SCOPE_KEY)
  return v === 'recompute' || v === 'future' ? v : 'future'
}

function loadReport(): GridResult | null {
  try {
    const raw = localStorage.getItem(REPORT_KEY)
    return raw ? JSON.parse(raw) as GridResult : null
  } catch { return null }
}

export const useTradingStore = defineStore('trading', () => {
  const loading = ref(false)
  const ticks = ref<Tick[]>([])
  const orderBook = ref<OrderBook | null>(null)
  const gridResult = ref<GridResult | null>(loadReport())
  const wsConnected = ref(false)
  const config = ref<GridConfig>(loadConfig())
  // 生效方式刷新后沿用上次选择（独立持久化，优先级高于配置内缓存）
  config.value.applyScope = loadScope()

  let ws: WebSocket | null = null
  function connectWS() {
    ws = new WebSocket(`ws://${location.hostname}:8000/ws`)
    ws.onopen = () => { wsConnected.value = true }
    ws.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data)
        if (d.ticks) ticks.value = d.ticks.slice(-60)
        if (d.orderBook) orderBook.value = d.orderBook
      } catch { /* ignore malformed frame */ }
    }
    ws.onclose = () => { wsConnected.value = false }
  }

  function persist() {
    localStorage.setItem(CONFIG_KEY, JSON.stringify(config.value))
    localStorage.setItem(SCOPE_KEY, config.value.applyScope)
  }

  /** 提交前校验；不合格时返回错误项并提示，不落盘、不请求 */
  function validate(): FieldError[] {
    const errs = validateConfig(config.value)
    if (errs.length) {
      ElMessage.error(`存在 ${errs.length} 项不合格，无法保存：${errs.map(e => e.message).join('；')}`)
    }
    return errs
  }

  /** 保存口径：取值合法才允许落盘；按所选生效方式决定是否重算已有报告 */
  async function saveParams(): Promise<boolean> {
    if (validate().length) return false
    persist()
    if (config.value.applyScope === 'recompute' && gridResult.value) {
      return await runBacktest(true)
    }
    ElMessage.success(config.value.applyScope === 'recompute'
      ? '口径已保存（暂无历史报告，将对后续回测生效）'
      : '口径已保存，仅对后续回测生效')
    return true
  }

  async function runBacktest(isRecompute = false): Promise<boolean> {
    if (validate().length) return false
    persist()
    loading.value = true
    try {
      const { data } = await axios.post<GridResult>('/api/backtest', config.value)
      gridResult.value = data
      localStorage.setItem(REPORT_KEY, JSON.stringify(data))
      ElMessage.success(isRecompute ? '已有报告已按新口径重算' : '回测完成')
      return true
    } catch (e: any) {
      const detail: FieldError[] | undefined = e?.response?.data?.detail
      if (Array.isArray(detail)) {
        ElMessage.error(`存在 ${detail.length} 项不合格，无法保存：${detail.map(d => d.message).join('；')}`)
      } else {
        ElMessage.error('回测请求失败')
      }
      return false
    } finally {
      loading.value = false
    }
  }

  function disconnectWS() { ws?.close(); ws = null; wsConnected.value = false }

  return { loading, ticks, orderBook, gridResult, wsConnected, config, connectWS, runBacktest, saveParams, validate, disconnectWS }
})
