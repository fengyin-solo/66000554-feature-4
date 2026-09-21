<template>
  <div class="panel">
    <h4>⚙️ 网格策略配置</h4>
    <el-form :model="store.config" label-width="90px" size="small" label-position="top">
      <el-row :gutter="8">
        <el-col :span="12">
          <el-form-item label="下限价格" :error="err('lowerPrice')">
            <el-input-number v-model="store.config.lowerPrice" :min="0.01" :max="200" :step="5" controls-position="right" @change="syncDerived" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="上限价格" :error="err('upperPrice')">
            <el-input-number v-model="store.config.upperPrice" :min="0.01" :max="200" :step="5" controls-position="right" @change="syncDerived" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-form-item label="网格间距口径" :error="err('spacingMode')">
        <el-radio-group v-model="store.config.spacingMode" size="small" @change="onModeChange">
          <el-radio-button value="count">按网格数量</el-radio-button>
          <el-radio-button value="spacing">按网格间距</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-row :gutter="8">
        <el-col :span="12" v-if="store.config.spacingMode === 'count'">
          <el-form-item label="网格数量" :error="err('gridCount')">
            <el-input-number v-model="store.config.gridCount" :min="2" :max="500" :step="1" controls-position="right" @change="onCountChange" />
          </el-form-item>
        </el-col>
        <el-col :span="12" v-else>
          <el-form-item label="网格间距" :error="err('gridSpacing')">
            <el-input-number v-model="store.config.gridSpacing" :min="0" :step="0.1" controls-position="right" @change="onSpacingChange" />
          </el-form-item>
        </el-col>
        <el-col :span="12"><el-form-item label="每格资金"><el-input-number v-model="store.config.capitalPerGrid" :min="0" :max="50000" :step="500" controls-position="right"/></el-form-item></el-col>
      </el-row>
      <el-form-item label="初始资金"><el-input-number v-model="store.config.initialCapital" :min="0" :max="1000000" :step="10000" controls-position="right"/></el-form-item>
      <el-button type="primary" @click="onRun" :loading="store.loading" block>🚀 运行回测</el-button>
    </el-form>

    <div class="grid-info" v-if="priceRange > 0">
      <div class="info-row">
        <span>网格间距</span>
        <span>{{ store.config.spacingMode === 'count' ? (priceRange / store.config.gridCount).toFixed(3) : Number(store.config.gridSpacing).toFixed(3) }}</span>
      </div>
      <div class="info-row">
        <span>实际网格数量</span>
        <span>{{ store.config.spacingMode === 'count' ? store.config.gridCount : derivedCount }}</span>
      </div>
      <div class="info-row">
        <span>总网格资金</span>
        <span>¥{{ (actualCount * store.config.capitalPerGrid).toLocaleString() }}</span>
      </div>
    </div>

    <el-divider class="cal-divider" />
    <h4>🧮 回测口径（按策略保存）</h4>
    <el-form label-width="90px" size="small" label-position="top">
      <el-row :gutter="8">
        <el-col :span="8">
          <el-form-item label="手续费率(%)" :error="err('caliber.feeRate')">
            <el-input-number v-model="feePct" :min="0" :max="1" :step="0.01" controls-position="right" @change="clearErr('caliber.feeRate')" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="滑点(%)" :error="err('caliber.slippagePct')">
            <el-input-number v-model="slipPct" :min="0" :max="2" :step="0.01" controls-position="right" @change="clearErr('caliber.slippagePct')" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="最小成交量" :error="err('caliber.minQuantity')">
            <el-input-number v-model="store.config.caliber.minQuantity" :min="0" :step="1" controls-position="right" @change="clearErr('caliber.minQuantity')" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="成交笔数口径" :error="err('tradeCountMode')">
        <el-radio-group v-model="store.config.tradeCountMode" size="small">
          <el-radio-button value="all">全部委托（含拒单）</el-radio-button>
          <el-radio-button value="filled">仅成交</el-radio-button>
          <el-radio-button value="roundtrip">完整买卖对</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="保存后生效方式">
        <el-radio-group v-model="applyMode" size="small">
          <el-radio value="future">只对后续回测生效</el-radio>
          <el-radio value="recompute">同时重算已有报告</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-button type="success" @click="onSave" :loading="store.loading" block>💾 保存口径</el-button>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useTradingStore } from '../store/trading'
import type { ApplyMode } from '../types'
const store = useTradingStore()

// 百分比展示（界面 %）与小数口径（费率/滑点）互换
const feePct = computed<number | undefined>({
  get: () => (store.config.caliber.feeRate == null ? undefined : store.config.caliber.feeRate * 100),
  set: (v) => { (store.config.caliber as any).feeRate = v == null ? undefined : v / 100 }
})
const slipPct = computed<number | undefined>({
  get: () => (store.config.caliber.slippagePct == null ? undefined : store.config.caliber.slippagePct * 100),
  set: (v) => { (store.config.caliber as any).slippagePct = v == null ? undefined : v / 100 }
})

const priceRange = computed(() => (store.config.upperPrice ?? 0) - (store.config.lowerPrice ?? 0))
const derivedCount = computed(() => {
  const s = store.config.gridSpacing
  return s > 0 && priceRange.value > 0 ? Math.max(1, Math.floor(priceRange.value / s)) : 0
})
const actualCount = computed(() =>
  store.config.spacingMode === 'count' ? store.config.gridCount || 0 : derivedCount.value)

function syncDerived() {
  // 切换/编辑后保证两种口径字段互相一致，提交给后端时不会出现矛盾值
  if (store.config.spacingMode === 'count' && store.config.gridCount > 0 && priceRange.value > 0) {
    store.config.gridSpacing = priceRange.value / store.config.gridCount
  } else if (store.config.gridSpacing > 0) {
    store.config.gridCount = derivedCount.value
  }
}
function onModeChange() { syncDerived() }
function onCountChange() { syncDerived() }
function onSpacingChange() { syncDerived() }

const err = (key: string) => store.caliberErrors[key] || ''
function clearErr(key: string) {
  if (store.caliberErrors[key]) {
    const next = { ...store.caliberErrors }
    delete next[key]
    store.caliberErrors = next
  }
}

const applyMode = computed<ApplyMode>({
  get: () => store.applyMode,
  set: (v) => store.setApplyMode(v)
})

async function onSave() {
  syncDerived()
  const ok = await store.saveCaliber()
  if (ok) {
    ElMessage.success(store.applyMode === 'recompute' && store.gridResult ? '口径已保存，已有报告已按新口径重算' : '口径已保存，将对后续回测生效')
  } else {
    const reasons = Object.values(store.caliberErrors)
    ElMessage.error(reasons.length ? `存在不合格项：${reasons.join('；')}` : '存在不合格项，请检查标红字段')
  }
}

async function onRun() {
  syncDerived()
  const ok = await store.runBacktest()
  if (!ok) {
    const reasons = Object.values(store.caliberErrors)
    ElMessage.error(reasons.length ? `存在不合格项：${reasons.join('；')}` : '存在不合格项，请检查标红字段')
  }
}
</script>
<style scoped>
.panel{background:#0f1535;border-radius:8px;padding:12px;border:1px solid #1e2a5a}
.panel h4{color:#4fc3f7;font-size:13px;margin-bottom:8px}
.cal-divider{margin:10px 0;border-color:#1e2a5a}
.grid-info{margin-top:12px;font-size:12px}
.info-row{display:flex;justify-content:space-between;padding:4px 0;color:#94a3b8;border-bottom:1px solid #1e2a5a33}
:deep(.el-form-item__error){position:static;font-size:11px;margin-top:2px}
:deep(.el-divider--horizontal){margin:10px 0}
</style>
