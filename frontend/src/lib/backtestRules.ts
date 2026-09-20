import type { GridConfig, FieldError } from '@/types'

export const GRID_MODE_OPTIONS = [
  { value: 'arithmetic', label: '等差网格（固定价格间距）' },
  { value: 'geometric', label: '等比网格（固定涨跌幅间距）' }
] as const

export const FILL_COUNT_OPTIONS = [
  { value: 'all', label: '全部成交（买+卖）' },
  { value: 'buy', label: '仅买入笔数' },
  { value: 'sell', label: '仅卖出笔数' },
  { value: 'round', label: '完整回合（配对卖出）' }
] as const

export const APPLY_SCOPE_OPTIONS = [
  { value: 'future', label: '仅对后续回测生效' },
  { value: 'recompute', label: '同时重算已有报告' }
] as const

interface NumericRule { label: string; min: number; max: number; integer?: boolean }

const BOUNDS: Record<string, NumericRule> = {
  lowerPrice: { label: '下限价格', min: 0.01, max: 100000 },
  upperPrice: { label: '上限价格', min: 0.01, max: 100000 },
  gridCount: { label: '网格数量', min: 1, max: 500, integer: true },
  capitalPerGrid: { label: '每格资金', min: 0.01, max: 1e12 },
  initialCapital: { label: '初始资金', min: 1, max: 1e12 },
  feeRate: { label: '手续费率(%)', min: 0, max: 1 },
  slippagePct: { label: '滑点(%)', min: 0, max: 5 },
  minQty: { label: '单笔最小成交量', min: 0, max: 1e9 }
}

function isFiniteNumber(v: unknown): boolean {
  return typeof v === 'number' && Number.isFinite(v)
}

/** 校验回测配置，返回所有不合格项；空数组表示通过（通过后才允许保存/回测） */
export function validateConfig(c: Partial<Record<string, unknown>>): FieldError[] {
  const errs: FieldError[] = []
  for (const [field, rule] of Object.entries(BOUNDS)) {
    const v = c[field]
    if (v === null || v === undefined || v === '') {
      errs.push({ field, message: `${rule.label}不能为空` })
    } else if (!isFiniteNumber(v)) {
      errs.push({ field, message: `${rule.label}必须为有效数字` })
    } else if (rule.integer && !Number.isInteger(v)) {
      errs.push({ field, message: `${rule.label}必须为整数` })
    } else {
      const num = v as number
      if (num < rule.min || num > rule.max) {
        errs.push({ field, message: `${rule.label}超出允许范围（${rule.min} ~ ${rule.max}）` })
      }
    }
  }
  if (isFiniteNumber(c.lowerPrice) && isFiniteNumber(c.upperPrice) && (c.upperPrice as number) <= (c.lowerPrice as number)) {
    errs.push({ field: 'upperPrice', message: '上限价格必须大于下限价格' })
  }
  if (!GRID_MODE_OPTIONS.some(o => o.value === c.gridMode)) {
    errs.push({ field: 'gridMode', message: '网格间距口径无效' })
  }
  if (!FILL_COUNT_OPTIONS.some(o => o.value === c.fillCountMode)) {
    errs.push({ field: 'fillCountMode', message: '成交笔数口径无效' })
  }
  if (!APPLY_SCOPE_OPTIONS.some(o => o.value === c.applyScope)) {
    errs.push({ field: 'applyScope', message: '生效方式无效' })
  }
  return errs
}

export function spacingText(c: Pick<GridConfig, 'lowerPrice' | 'upperPrice' | 'gridCount' | 'gridMode'>): string {
  if (!isFiniteNumber(c.lowerPrice) || !isFiniteNumber(c.upperPrice) ||
      !isFiniteNumber(c.gridCount) || c.gridCount <= 0 || c.upperPrice <= c.lowerPrice) {
    return '—'
  }
  if (c.gridMode === 'geometric') {
    const ratio = (c.upperPrice / c.lowerPrice) ** (1 / c.gridCount)
    return `${((ratio - 1) * 100).toFixed(3)}%（等比）`
  }
  return `${((c.upperPrice - c.lowerPrice) / c.gridCount).toFixed(4)}（等差）`
}
