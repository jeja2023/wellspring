import type { CaseInformation } from './spreadsheet'
import { RequestCancelled } from '../../shared/api/client'

export function parseWorkbookInWorker(buffer: ArrayBuffer, signal: AbortSignal): Promise<CaseInformation[]> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) { reject(new RequestCancelled()); return }
    const worker = new Worker(new URL('./spreadsheet.worker.ts', import.meta.url), { type: 'module' })
    const finish = (error?: Error, records?: CaseInformation[]) => {
      clearTimeout(timer); signal.removeEventListener('abort', abort); worker.terminate()
      if (error) reject(error); else resolve(records!)
    }
    const abort = () => finish(new RequestCancelled())
    const timer = setTimeout(() => finish(new Error('文件解析超过 20 秒，已停止；请缩小文件后重试。')), 20000)
    signal.addEventListener('abort', abort, { once: true })
    worker.onmessage = event => event.data.error ? finish(new Error(event.data.error)) : finish(undefined, event.data.records)
    worker.onerror = () => finish(new Error('文件解析失败，请检查文件或更新浏览器。'))
    worker.postMessage({ buffer, existingNumbers: [] }, [buffer])
  })
}
