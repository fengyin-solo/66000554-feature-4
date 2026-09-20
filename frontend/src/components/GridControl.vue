<template>
  <div class="panel">
    <h4>⚙️ 网格策略配置</h4>
    <el-form ref="formRef" :model="store.config" :rules="rules" size="small" label-position="top">
      <el-divider content-position="left">策略参数</el-divider>
      <el-row :gutter="8">
        <el-col :span="12"><el-form-item label="下限价格" prop="lowerPrice"><el-input-number v-model="store.config.lowerPrice" :min="0.01" :max="100000" :step="5" controls-position="right" class="full"/></el-form-item></el-col>
        <el-col :span="12"><el-form-item label="上限价格" prop="upperPrice"><el-input-number v-model="store.config.upperPrice" :min="0.01" :max="100000" :step="5" controls-position="right" class="full"/></el-form-item></el-col>
      </el-row>
      <el-row :gutter="8">
        <el-col :span="12"><el-form-item label="网格数量" prop="gridCount"><el-input-number v-model="store.config.gridCount" :min="1" :max="500" :step="1" controls-position="right" class="full"/></el-form-item></el-col>
        <el-col :span="12"><el-form-item label="每格资金" prop="capitalPerGrid"><el-input-number v-model="store.config.capitalPerGrid" :min="0.01" :max="50000" :step="500" controls-position="right" class="full"/></el-form-item></el-col>
      </el-row>
      <el-form-item label="初始资金" prop="initialCapital"><el-input-number v-model="store.config.initialCapital" :min="1" :max="1000000" :step="10000" controls-position="right" class="full"/></el-form-item>

      <el-divider content-position="left">回测口径（按策略可调）</el-divider>
      <el-row :gutter="8">
        <el-col :span="8">
          <el-form-item label="手续费率 %" prop="feeRate">
            <el-input-number v-model="store.config.feeRate" :min="0" :max="1" :step="0.01" :precision="4" controls-position="right" class="full"/>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="滑点 %" prop="slippagePct">
            <el-input-number v-model="store.config.slippagePct" :min="0" :max="5" :step="0.01" :precision="4" controls-position="right" class="full"/>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="单笔最小成交量" prop="minQty">
            <el-input-number v-model="store.config.minQty" :min="0" :max="1000000000" :step="1" controls-position="right" class="full"/>
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="网格间距口径" prop="gridMode">
        <el-select v-model="store.config.gridMode" class="full">
          <el-option v-for="o in gridModeOptions" :key="o.value" :value="o.value" :label="o.label"/>
        </el-select>
      </el-form-item>
      <el-form-item label="成交笔数口径" prop="fillCountMode">
        <el-select v-model="store.config.fillCountMode" class="full">
          <el-option v-for="o in fillCountOptions" :key="o.value" :value="o.value" :label="o.label"/>
        </el-select>
      </el-form-item>

      <el-divider content-position="left">生效方式</el-divider>
      <el-form-item prop="applyScope" class="scope-item">
        <el-radio-group v-model="store.config.applyScope" @change="onScopeChange">
          <el-radio value="future">仅对后续回测生效</el-radio>
          <el-radio value="recompute">同时重算已有报告</el-radio>
        </el-radio-group>
      </el-form-item>

      <div class="btn-row">
        <el-button type="success" plain @click="store.saveParams" :loading="store.loading">💾 保存口径</el-button>
        <el-button type="primary" @click="store.runBacktest()" :loading="store.loading">🚀 运行回测</el-button>
      </div>
    </el-form>
    <div class="grid-info">
      <div class="info-row"><span>网格间距</span><span>{{ spacingText(store.config) }}</span></div>
      <div class="info-row"><span>总网格资金</span><span>¥{{ validTotal ? (store.config.gridCount*store.config.capitalPerGrid).toLocaleString() : '—' }}</span></div>
      <div class="info-row"><span>成交笔数口径</span><span>{{ fillLabel }}</span></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { useTradingStore } from '../store/trading'
import { validateConfig, spacingText, GRID_MODE_OPTIONS, FILL_COUNT_OPTIONS } from '../lib/backtestRules'

const store = useTradingStore()
const formRef = ref<FormInstance>()

const gridModeOptions = GRID_MODE_OPTIONS
const fillCountOptions = FILL_COUNT_OPTIONS

const validTotal = computed(() =>
  Number.isFinite(store.config.gridCount) && Number.isFinite(store.config.capitalPerGrid))
const fillLabel = computed(() =>
  FILL_COUNT_OPTIONS.find(o => o.value === store.config.fillCountMode)?.label ?? '—')

// el-form 行内校验：与 store.validate / 后端 validate_config 同源
function fieldValidator(field: string) {
  return (_rule: unknown, value: unknown, cb: (e?: Error) => void) => {
    const errs = validateConfig({ ...store.config, [field]: value })
    const hit = errs.find(e => e.field === field)
    cb(hit ? new Error(hit.message) : undefined)
  }
}

const rules: FormRules = {
  lowerPrice: [{ validator: fieldValidator('lowerPrice'), trigger: 'change' }],
  upperPrice: [{ validator: fieldValidator('upperPrice'), trigger: 'change' }],
  gridCount: [{ validator: fieldValidator('gridCount'), trigger: 'change' }],
  capitalPerGrid: [{ validator: fieldValidator('capitalPerGrid'), trigger: 'change' }],
  initialCapital: [{ validator: fieldValidator('initialCapital'), trigger: 'change' }],
  feeRate: [{ validator: fieldValidator('feeRate'), trigger: 'change' }],
  slippagePct: [{ validator: fieldValidator('slippagePct'), trigger: 'change' }],
  minQty: [{ validator: fieldValidator('minQty'), trigger: 'change' }],
  gridMode: [{ validator: fieldValidator('gridMode'), trigger: 'change' }],
  fillCountMode: [{ validator: fieldValidator('fillCountMode'), trigger: 'change' }]
}

// 生效方式本身也要持久化，刷新后沿用上次选择；此处只记录选择，不触发口径保存
function onScopeChange() {
  localStorage.setItem('grid:applyScope', store.config.applyScope)
}
</script>
<style scoped>
.panel{background:#0f1535;border-radius:8px;padding:12px;border:1px solid #1e2a5a}
.panel h4{color:#4fc3f7;font-size:13px;margin-bottom:8px}
:deep(.el-divider__text){background:#0f1535;color:#64748b;font-size:11px}
.full{width:100%}
.btn-row{display:flex;gap:8px}
.btn-row .el-button{flex:1}
.scope-item :deep(.el-radio){display:flex;margin:2px 0;height:22px}
.grid-info{margin-top:4px;font-size:12px}
.info-row{display:flex;justify-content:space-between;padding:4px 0;color:#94a3b8;border-bottom:1px solid #1e2a5a33}
</style>
