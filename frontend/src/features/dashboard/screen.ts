export type Metric = { key: string; label: string; unit: string; total: number; period_count: number }
export type Distribution = { key: string; label: string; value: number }
export type Overview = {
  generated_at: string
  organization: string
  timezone: string
  date_basis: string
  range: { days: 7 | 30 | 90; start_date: string; end_date: string }
  metrics: Metric[]
  trend: { dates: string[]; series: { key: string; label: string; values: number[] }[] }
  breakdowns: Record<string, Distribution[]>
}

export type ChartBox = { left: number; top: number; width: number; height: number }

export const colors = [
  'var(--ws-series-1)',
  'var(--ws-series-2)',
  'var(--ws-series-3)',
  'var(--ws-series-4)',
  'var(--ws-series-5)',
  'var(--ws-series-6)',
]

const wideChartBox: ChartBox = { left: 44, top: 24, width: 1012, height: 186 }

export function chartX(index: number, count: number, box: ChartBox = wideChartBox): number {
  return box.left + (index * box.width) / Math.max(1, count - 1)
}

export function chartY(value: number, maximum: number, box: ChartBox = wideChartBox): number {
  return box.top + box.height - (value * box.height) / Math.max(1, maximum)
}

export function linePath(values: number[], maximum: number, box: ChartBox = wideChartBox): string {
  return values
    .map((value, index) => `${index ? 'L' : 'M'}${chartX(index, values.length, box).toFixed(1)},${chartY(value, maximum, box).toFixed(1)}`)
    .join(' ')
}

export function areaPath(values: number[], maximum: number, box: ChartBox = wideChartBox): string {
  if (!values.length) return ''
  const line = linePath(values, maximum, box)
  const baseY = (box.top + box.height).toFixed(1)
  const firstX = chartX(0, values.length, box).toFixed(1)
  const lastX = chartX(values.length - 1, values.length, box).toFixed(1)
  return `${line} L${lastX},${baseY} L${firstX},${baseY} Z`
}

export function seriesAxisMax(values: number[], step = 2): number {
  const peak = Math.max(0, ...values)
  return Math.max(step, Math.ceil(peak / step) * step)
}

export type DonutSegment = {
  key: string
  label: string
  value: number
  percent: number
  color: string
  dashArray: string
  dashOffset: number
}

export function buildDonutSegments(items: Distribution[], radius = 38): { total: number; segments: DonutSegment[] } {
  const total = items.reduce((sum, item) => sum + item.value, 0)
  if (!total) return { total: 0, segments: [] }
  const circumference = 2 * Math.PI * radius
  const nonZeroCount = items.filter((item) => item.value > 0).length
  const gap = nonZeroCount > 1 ? 2.4 : 0
  let accumulated = 0
  const segments: DonutSegment[] = items.map((item, index) => {
    const ratio = item.value / total
    const rawArc = ratio * circumference
    const arc = item.value > 0 ? Math.max(1.5, rawArc - gap) : 0
    const segment: DonutSegment = {
      key: item.key,
      label: item.label,
      value: item.value,
      percent: Math.round(ratio * 1000) / 10,
      color: colors[index % colors.length],
      dashArray: `${arc.toFixed(2)} ${circumference.toFixed(2)}`,
      dashOffset: -accumulated,
    }
    accumulated += rawArc
    return segment
  })
  return { total, segments }
}
