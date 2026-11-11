/** 在交给 ExcelJS 前流式核验实际解压体积，避免仅检查压缩文件大小。 */
export async function validateZipBudget(buffer: ArrayBuffer): Promise<void> {
  // Node/ExcelJS 测试返回 Buffer，浏览器返回 ArrayBuffer；统一为独立字节视图。
  if (!(buffer instanceof ArrayBuffer)) buffer = new Uint8Array(buffer).buffer
  const view = new DataView(buffer)
  const maxBytes = 16 * 1024 * 1024, maxEntry = 8 * 1024 * 1024
  if (buffer.byteLength > 2 * 1024 * 1024) throw new Error('文件不能超过 2 MB。')
  const invalid = () => new Error('Excel 压缩包无效或使用了不支持的格式。')
  let end = -1
  for (let offset = buffer.byteLength - 22; offset >= Math.max(0, buffer.byteLength - 65557); offset--) {
    if (view.getUint32(offset, true) === 0x06054b50 && offset + 22 + view.getUint16(offset + 20, true) === buffer.byteLength) { end = offset; break }
  }
  if (end < 0) throw invalid()
  const count = view.getUint16(end + 10, true), directory = view.getUint32(end + 16, true)
  if (view.getUint16(end + 4, true) || view.getUint16(end + 6, true) || count !== view.getUint16(end + 8, true) || count > 256) throw invalid()
  if (directory + view.getUint32(end + 12, true) !== end) throw invalid()
  let offset = directory, declaredTotal = 0, actualTotal = 0
  for (let index = 0; index < count; index++) {
    if (offset + 46 > end || view.getUint32(offset, true) !== 0x02014b50) throw invalid()
    const flags = view.getUint16(offset + 8, true), method = view.getUint16(offset + 10, true)
    const compressed = view.getUint32(offset + 20, true), declared = view.getUint32(offset + 24, true)
    const local = view.getUint32(offset + 42, true)
    declaredTotal += declared
    if (declared > maxEntry || declaredTotal > maxBytes) throw new Error('Excel 解压后内容过大，最多支持 16 MB。')
    if ((flags & 1) || ![0, 8].includes(method) || local + 30 > directory || view.getUint32(local, true) !== 0x04034b50) throw invalid()
    const start = local + 30 + view.getUint16(local + 26, true) + view.getUint16(local + 28, true)
    if (start + compressed > directory) throw invalid()
    const blob = new Blob([buffer.slice(start, start + compressed)])
    let stream = blob.stream()
    if (method === 8) {
      try { stream = stream.pipeThrough(new DecompressionStream('deflate-raw')) }
      catch { throw new Error('浏览器不支持安全解析此文件，请更新浏览器后重试。') }
    }
    const reader = stream.getReader()
    let actual = 0
    try {
      while (true) {
        const chunk = await reader.read()
        if (chunk.done) break
        actual += chunk.value.byteLength; actualTotal += chunk.value.byteLength
        if (actual > maxEntry || actualTotal > maxBytes) { await reader.cancel(); throw new Error('Excel 实际解压内容过大，已停止解析。') }
      }
    } finally { reader.releaseLock() }
    if (actual !== declared) throw invalid()
    offset += 46 + view.getUint16(offset + 28, true) + view.getUint16(offset + 30, true) + view.getUint16(offset + 32, true)
  }
  if (offset !== end) throw invalid()
}
