/** API 时间以 UTC 传输，界面统一使用北京时间。 */
export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return '—'
  const instant = /(?:Z|[+-]\d\d:\d\d)$/i.test(value) ? value : `${value}Z`
  const date = new Date(instant)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
}
