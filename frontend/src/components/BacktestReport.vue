<template>
  <div class="panel" v-if="store.gridResult">
    <h4>📋 回测报告</h4>
    <div v-if="stale" class="stale-tip">
      ⚠️ 当前口径与本报告不一致（已选择「仅对后续回测生效」），运行回测或保存时选择重算后本报告才会刷新
    </div>
    <div class="metric-grid">
      <div class="metric">
        <div class="m-val" :class="store.gridResult.totalProfit>=0?'profit':'loss'">¥{{ store.gridResult.totalProfit.toFixed(0) }}</div>
        <div class="m-label">总盈亏</div>
      </div>
      <div class="metric"><div class="m-val" :class="store.gridResult.returnRate>=0?'profit':'loss'">{{ store.gridResult.returnRate.toFixed(2) }}%</div><div class="m-label">收益率</div></div>
      <div class="metric"><div class="m-val">{{ store.gridResult.sharpeRatio.toFixed(2) }}</div><div class="m-label">夏普比率</div></div>
      <div class="metric"><div class="m-val loss">{{ store.gridResult.maxDrawdown.toFixed(2) }}%</div><div class="m-label">最大回撤</div></div>
      <div class="metric"><div class="m-val">{{ store.gridResult.winRate.toFixed(1) }}%</div><div class="m-label">胜率</div></div>
      <div class="metric"><div class="m-val">{{ store.gridResult.fillCount }}</div><div class="m-label">成交笔数 · {{ countModeShort }}</div></div>
    </div>

    <div class="reconcile">
      <div class="section-title">口径与对账</div>
      <div class="chip-row">
        <span class="chip">手续费 {{ store.gridResult.params.feeRate }}%</span>
        <span class="chip">滑点 {{ store.gridResult.params.slippagePct }}%</span>
        <span class="chip">最小量 {{ store.gridResult.params.minQty }}</span>
        <span class="chip">{{ store.gridResult.params.gridModeLabel }}</span>
        <span class="chip">间距 {{ store.gridResult.params.spacingText }}</span>
        <span class="chip">{{ store.gridResult.params.fillCountModeLabel }}</span>
      </div>
      <div class="rec-row"><span>已实现盈亏</span><b :class="store.gridResult.realizedProfit>=0?'profit':'loss'">¥{{ store.gridResult.realizedProfit.toFixed(2) }}</b></div>
      <div class="rec-row"><span>浮动盈亏（{{ store.gridResult.finalHoldings.toFixed(2) }} @ ¥{{ store.gridResult.finalPrice }}）</span><b :class="store.gridResult.floatingProfit>=0?'profit':'loss'">¥{{ store.gridResult.floatingProfit.toFixed(2) }}</b></div>
      <div class="rec-row total"><span>合计 = 总盈亏</span><b :class="store.gridResult.totalProfit>=0?'profit':'loss'">¥{{ store.gridResult.totalProfit.toFixed(2) }}</b></div>
      <div class="rec-row"><span>买入 / 卖出成交</span><b>{{ store.gridResult.buyCount }} / {{ store.gridResult.sellCount }}</b></div>
      <div class="rec-row" v-if="store.gridResult.rejectedCount"><span class="warn">未成交（低于最小量/资金不足）</span><b class="warn">{{ store.gridResult.rejectedCount }}</b></div>
    </div>

    <div ref="eqChart" class="chart"></div>
    <div class="order-list" v-if="store.gridResult.orders.length">
      <div class="section-title">最近成交 / 拒单</div>
      <div v-for="o in store.gridResult.orders.slice(-8).reverse()" :key="o.id" class="order-row" :class="[o.side.toLowerCase(), o.status.toLowerCase()]">
        <span class="o-side">{{ o.side }}</span>
        <span class="o-price">@¥{{ o.price }}</span>
        <span class="o-qty">{{ o.quantity.toFixed(2) }}</span>
        <span class="o-fee">费¥{{ (o.fee ?? 0).toFixed(2) }}</span>
        <span v-if="o.status==='REJECTED'" class="o-reason">拒单：{{ o.reason }}</span>
        <span class="o-profit" :class="o.profit>=0?'profit':'loss'" v-else-if="o.side==='SELL'">{{ o.profit>=0?'+':'' }}¥{{ o.profit.toFixed(2) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import { useTradingStore } from '../store/trading'

const store = useTradingStore()
const eqChart = ref<HTMLDivElement>()
let inst: echarts.ECharts | null = null

const countModeShort = computed(() => {
  const r = store.gridResult
  if (!r) return ''
  return ({ all: '买+卖', buy: '买入', sell: '卖出', round: '回合' } as const)[r.params.fillCountMode]
})

// 报告口径与当前编辑口径是否不一致（future 模式下报告会滞后）
const stale = computed(() => {
  const r = store.gridResult
  if (!r) return false
  const c = store.config
  return r.params.feeRate !== c.feeRate ||
    r.params.slippagePct !== c.slippagePct ||
    r.params.minQty !== c.minQty ||
    r.params.gridMode !== c.gridMode ||
    r.params.fillCountMode !== c.fillCountMode ||
    r.params.lowerPrice !== c.lowerPrice ||
    r.params.upperPrice !== c.upperPrice ||
    r.params.gridCount !== c.gridCount ||
    r.params.capitalPerGrid !== c.capitalPerGrid ||
    r.params.initialCapital !== c.initialCapital
})

function updateEq() {
  if (!inst || !store.gridResult) return
  const eq = store.gridResult.equityCurve
  inst.setOption({
    backgroundColor: 'transparent', grid: { left: 45, right: 10, top: 5, bottom: 20 },
    xAxis: { type: 'category', data: eq.map((_, i) => i), show: false },
    yAxis: { type: 'value', axisLabel: { color: '#94a3b8', fontSize: 9 } },
    series: [{
      type: 'line', data: eq, symbol: 'none', lineStyle: { color: '#4fc3f7', width: 1 },
      areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(79,195,247,0.2)' }, { offset: 1, color: 'rgba(79,195,247,0)' }]) }
    }], animation: false
  })
}
watch(() => store.gridResult, () => { if (store.gridResult) setTimeout(updateEq, 50) })
onMounted(() => {
  nextTick(() => {
    if (eqChart.value && !inst) inst = echarts.init(eqChart.value)
    updateEq()
  })
})
onUnmounted(() => inst?.dispose())
</script>

<style scoped>
.panel{background:#0f1535;border-radius:8px;padding:12px;border:1px solid #1e2a5a}
.panel h4{color:#4fc3f7;font-size:13px;margin-bottom:8px}
.stale-tip{background:#f59e0b1a;border:1px solid #f59e0b55;color:#fbbf24;font-size:11px;padding:6px 8px;border-radius:4px;margin-bottom:8px;line-height:1.4}
.metric-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px}
.metric{text-align:center;padding:8px;background:#0a0e27;border-radius:6px}
.m-val{font-size:18px;font-weight:700}.m-val.profit{color:#22c55e}.m-val.loss{color:#ef4444}
.m-label{font-size:10px;color:#64748b;margin-top:2px}
.reconcile{margin-top:8px}
.chip-row{display:flex;flex-wrap:wrap;gap:4px;margin:4px 0 6px}
.chip{font-size:10px;color:#93c5fd;background:#1e2a5a55;border:1px solid #1e2a5a;border-radius:10px;padding:1px 8px}
.rec-row{display:flex;justify-content:space-between;font-size:11px;color:#94a3b8;padding:2px 2px}
.rec-row.total{border-top:1px dashed #1e2a5a;margin-top:2px;padding-top:4px;color:#e0e0e0}
.rec-row b{font-weight:600}.profit{color:#22c55e}.loss{color:#ef4444}.warn{color:#f59e0b}
.chart{width:100%;height:120px;margin-top:8px}
.order-row{display:flex;gap:8px;align-items:center;padding:3px 6px;font-size:11px;border-radius:3px;margin:1px 0}
.order-row.buy.filled{background:#22c55e15}.order-row.sell.filled{background:#ef444415}
.order-row.rejected{background:#6b728015;opacity:.75}
.o-side{font-weight:700;min-width:34px;color:#e0e0e0}
.o-price{color:#94a3b8}.o-qty{color:#64748b}.o-fee{color:#475569;font-size:10px}
.o-reason{color:#f59e0b;margin-left:auto;font-size:10px}
.o-profit{margin-left:auto}.o-profit.profit{color:#22c55e}.o-profit.loss{color:#ef4444}
.section-title{font-size:11px;color:#64748b;margin:6px 0 4px}
</style>
