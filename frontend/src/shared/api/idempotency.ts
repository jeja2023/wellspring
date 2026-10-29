/** 为业务请求生成不可预测的标识，支持隔离内网的 HTTP 环境。 */
export function newIdempotencyKey(): string {
  if (!globalThis.crypto?.getRandomValues) {
    throw new Error('浏览器不支持安全随机数，无法安全提交操作。')
  }
  const bytes = new Uint8Array(16)
  globalThis.crypto.getRandomValues(bytes)
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
