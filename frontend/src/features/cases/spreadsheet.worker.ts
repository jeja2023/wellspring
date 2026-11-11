import { parseWorkbook } from './spreadsheet'

self.onmessage = async (event: MessageEvent<{ buffer: ArrayBuffer; existingNumbers: string[] }>) => {
  try { self.postMessage({ records: await parseWorkbook(event.data.buffer, event.data.existingNumbers) }) }
  catch (error) { self.postMessage({ error: error instanceof Error ? error.message : '解析 Excel 文件失败' }) }
}
