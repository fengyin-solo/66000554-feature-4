<template>
  <div class="panel" v-if="store.gridResult">
    <h4>📋 回测报告</h4>

    <!-- 报告口径快照：成交明细与绩效指标均按此口径计算 -->
    <div class="caliber-snap">
      <span>手续费率 {{ (r.caliber.feeRate*100).toFixed(3) }}%</span>
      <span>滑点 {{ (r.caliber.slippagePct*100).toFixed(3) }}%</span>
      <span>最小量 {{ r.caliber.minQuantity }}</span>
      <span>间距 {{ r.gridSpacing }}</span>
      <span>{{ tradeCountLabel }} {{ r.tradeCount }}</span>
    </div>

    <!-- 当前已保存口径与报告口径不一致：该报告仍是旧口径（只对后续生效）时给出 -->
    <el-alert
      v-if="caliberMismatch"
      type="warning" :closable="false" show-icon class="stale-alert"
      title="当前口径与本报告口径不一致，绩效指标与明细仍按报告口径展示">
      <el-button size="small" type="warning" :loading="store.loading" @click="onRecompute">按当前口径重算</el-button>
    </el-alert>

    <div class="metric-grid">
      <div class="metric">
        <div class="m-val" :class="r.totalProfit>=0?'profit':'loss'">¥{{ r.totalProfit.toFixed(0) }}</div>
        <div class="m-label">总盈亏</div>
      </div>
      <div class="metric"><div class="m-val" :class="r.returnRate>=0?'profit':'loss'">{{ r.returnRate.toFixed(2) }}%</div><div class="m-label">收益率</div></div>
      <div class="metric"><div class="m-val">{{ r.sharpeRatio.toFixed(2) }}</div><div class="m-label">夏普比率</div></div>
      <div class="metric"><div class="m-val loss">{{ r.maxDrawdown.toFixed(2) }}%</div><div class="m-label">最大回撤</div></div>
      <div class="metric"><div class="m-val">{{ r.winRate.toFixed(1) }}%</div><div class="m-label">胜率</div></div>
      <div class="metric"><div class="m-val">{{ r.tradeCount }}</div><div class="m-label">成交笔数（{{ tradeCountShort }}）</div></div>
    </div>
    <div ref="eqChart" class="chart"></div>

    <div class="fee-row">
      <span>累计手续费：¥{{ r.totalFees.toFixed(2) }}（含在总盈亏内）</span>
      <span>拒单：{{ rejectedCount }} 笔</span>
    </div>

    <div class="order-list" v-if="r.orders.length">
      <div class="section-title">最近成交（明细与绩效同一口径）</div>
      <div v-for="o in r.orders.slice(-10).reverse()" :key="o.id" class="order-row" :class="[o.side, o.status]">
        <span class="o-side" :class="o.side">{{ o.side }}</span>
        <span class="o-price">@¥{{ o.price }}</span>
        <span class="o-qty">{{ o.quantity.toFixed(2) }}</span>
        <span class="o-fee">费 ¥{{ o.fee.toFixed(2) }}</span>
        <span v-if="o.status==='REJECTED'" class="o-reject">拒单：{{ o.reason }}</span>
        <span class="o-profit" :class="o.profit>=0?'profit':'loss'" v-else-if="o.side==='SELL'">
          {{ o.profit>=0?'+':'' }}¥{{ o.profit.toFixed(2) }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import { useTradingStore } from '../store/trading'
import type { TradeCountMode } from '../types'
const store = useTradingStore(); const eqChart = ref<HTMLDivElement>(); let inst: echarts.ECharts | null = null

const r = computed(() => store.gridResult!)

const TRADE_LABELS: Record<TradeCountMode, string> = {
  all: '全部委托（含拒单）', filled: '仅成交', roundtrip: '完整买卖对'
}
const TRADE_SHORT: Record<TradeCountMode, string> = {
  all: '含拒单', filled: '仅成交', roundtrip: '买卖对'
}
const tradeCountLabel = computed(() => TRADE_LABELS[r.value.tradeCountMode])
const tradeCountShort = computed(() => TRADE_SHORT[r.value.tradeCountMode])
const rejectedCount = computed(() => r.value.orders.filter(o => o.status === 'REJECTED').length)

// 报告口径与当前配置口径是否一致（当前口径只对后续回测生效时，旧报告会显示为不一致）
const caliberMismatch = computed(() => {
  const c = store.config.caliber, s = r.value.caliber
  return c.feeRate !== s.feeRate || c.slippagePct !== s.slippagePct || c.minQuantity !== s.minQuantity ||
         store.config.tradeCountMode !== r.value.tradeCountMode ||
         store.config.spacingMode !== r.value.spacingMode
})

async function onRecompute() { await store.runBacktest() }

function updateEq() {
  if (!inst||!store.gridResult) return
  const eq = store.gridResult.equityCurve
  inst.setOption({
    backgroundColor:'transparent',grid:{left:45,right:10,top:5,bottom:20},
    xAxis:{type:'category',data:eq.map((_,i)=>i),show:false},
    yAxis:{type:'value',axisLabel:{color:'#94a3b8',fontSize:9}},
    series:[{type:'line',data:eq,symbol:'none',lineStyle:{color:'#4fc3f7',width:1},
      areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'rgba(79,195,247,0.2)'},{offset:1,color:'rgba(79,195,247,0)'}])}
    }],animation:false
  })
}
watch(()=>store.gridResult,(x)=>{
  if (!x) return
  setTimeout(() => {
    if (!inst && eqChart.value) inst = echarts.init(eqChart.value)
    updateEq()
  }, 50)
})
onMounted(() => { if (store.gridResult && eqChart.value) { inst = echarts.init(eqChart.value); updateEq() } })
onUnmounted(()=>inst?.dispose())
</script>

<style scoped>
.panel{background:#0f1535;border-radius:8px;padding:12px;border:1px solid #1e2a5a}
.panel h4{color:#4fc3f7;font-size:13px;margin-bottom:8px}
.caliber-snap{display:flex;flex-wrap:wrap;gap:4px 10px;font-size:10px;color:#94a3b8;background:#0a0e27;border-radius:6px;padding:6px 8px;margin-bottom:8px}
.stale-alert{margin-bottom:8px}
.stale-alert :deep(.el-alert__content){display:flex;align-items:center;gap:8px}
.metric-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px}
.metric{text-align:center;padding:8px;background:#0a0e27;border-radius:6px}
.m-val{font-size:18px;font-weight:700}.m-val.profit{color:#22c55e}.m-val.loss{color:#ef4444}
.m-label{font-size:10px;color:#64748b;margin-top:2px}
.chart{width:100%;height:120px;margin-top:8px}
.fee-row{display:flex;justify-content:space-between;font-size:10px;color:#64748b;margin-top:6px;padding:0 2px}
.order-row{display:flex;gap:8px;align-items:center;padding:3px 6px;font-size:11px;border-radius:3px;margin:1px 0}
.order-row.BUY.FILLED{background:#22c55e15}.order-row.SELL.FILLED{background:#ef444415}
.order-row.REJECTED{background:#64748b22;opacity:.75}
.o-side{font-weight:700;min-width:30px}.o-side.BUY{color:#22c55e}.o-side.SELL{color:#ef4444}
.o-price{color:#94a3b8}.o-qty{color:#64748b}.o-fee{color:#64748b;font-size:10px}
.o-profit{margin-left:auto}.o-profit.profit{color:#22c55e}.o-profit.loss{color:#ef4444}
.o-reject{margin-left:auto;color:#f59e0b;font-size:10px}
.section-title{font-size:11px;color:#64748b;margin:6px 0 4px}
</style>
