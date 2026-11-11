export type ErrorDetail = { field?: string; code?: string; message?: string }
export class ApiError extends Error {
  constructor(message: string, public definitive: boolean, public status?: number,
    public code = '', public details: ErrorDetail[] = [], public requestId = '') {
    const fields = details.slice(0, 5).map(detail => {
      const field = (detail.field ?? '').replace(/^rows\.(\d+)\./, (_, row) => `Excel 第 ${Number(row) + 2} 行 · `)
      return `${field}：${detail.message || '字段格式或取值不正确'}`
    })
    super([message, ...fields, ...(requestId ? [`请求编号：${requestId}`] : [])].join('；'))
  }
}
export class RequestCancelled extends Error {
  constructor() { super('请求已取消') }
}
export function isCancelled(error: unknown): error is RequestCancelled { return error instanceof RequestCancelled }
export type RequestOptions = RequestInit & { timeoutMs?: number; onUnauthorized?: (token: string) => void }
export type ApiRequest = <T = any>(path: string, options?: RequestOptions) => Promise<T>

export async function request<T = any>(path: string, token: string, options: RequestOptions = {}): Promise<T> {
  const { timeoutMs = 30000, onUnauthorized, signal, ...init } = options
  const controller = new AbortController()
  const abort = () => controller.abort()
  signal?.addEventListener('abort', abort, { once: true })
  if (signal?.aborted) controller.abort()
  let timedOut = false
  const timer = setTimeout(() => { timedOut = true; controller.abort() }, timeoutMs)
  const headers = new Headers(init.headers)
  headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const writing = !['GET', 'HEAD'].includes((init.method || 'GET').toUpperCase()) && !/\/(search|export|deleted)$/.test(path)
  try {
    let response: Response
    try { response = await fetch(`/api${path}`, { ...init, headers, signal: controller.signal }) }
    catch {
      if (signal?.aborted) throw new RequestCancelled()
      throw new ApiError(timedOut
        ? writing ? '请求超时，操作结果尚未确认；请保留当前输入并重试。' : '查询超时，请重试。'
        : writing ? '网络中断，操作结果尚未确认；请保留当前输入并重试。' : '网络中断，查询失败，请重试。', false)
    }
    if (controller.signal.aborted) {
      if (signal?.aborted) throw new RequestCancelled()
      throw new ApiError('请求超时，操作结果尚未确认；请保留当前输入并重试。', false)
    }
    let data: any
    try { data = await response.json() }
    catch { if (signal?.aborted) throw new RequestCancelled(); throw new ApiError('服务返回异常，操作结果尚未确认；请保留当前输入并重试。', false, response.status, '', [], response.headers.get('X-Request-ID') || '') }
    if (signal?.aborted) throw new RequestCancelled()
    if (timedOut) throw new ApiError('请求超时，操作结果尚未确认；请保留当前输入并重试。', false)
    if (!response.ok) {
      if (response.status === 401 && token) onUnauthorized?.(token)
      throw new ApiError(typeof data?.message === 'string' ? data.message : '请求失败，请检查输入',
        response.status < 500 && data?.code !== 'IDEMPOTENCY_IN_PROGRESS', response.status,
        typeof data?.code === 'string' ? data.code : '', Array.isArray(data?.details) ? data.details : [],
        typeof data?.request_id === 'string' ? data.request_id : response.headers.get('X-Request-ID') || '')
    }
    return data as T
  } finally { clearTimeout(timer); signal?.removeEventListener('abort', abort) }
}

/** 会话版本校验与取消共同阻止已经完成网络读取的旧响应回写。 */
export function createRequestScope(getToken: () => string, unauthorized?: (token: string) => void) {
  let generation = 0
  const controllers = new Set<AbortController>()
  function capture() {
    const expected = generation, token = getToken()
    return () => expected === generation && token === getToken()
  }
  function cancel() { generation++; for (const controller of controllers) controller.abort(); controllers.clear() }
  const api: ApiRequest = async <T>(path: string, options: RequestOptions = {}) => {
    const current = capture(), controller = new AbortController()
    const abort = () => controller.abort()
    options.signal?.addEventListener('abort', abort, { once: true })
    if (options.signal?.aborted) controller.abort()
    controllers.add(controller)
    try {
      const result = await request<T>(path, getToken(), { ...options, signal: controller.signal, onUnauthorized: unauthorized })
      if (!current() || controller.signal.aborted) throw new RequestCancelled()
      return result
    } catch (error) { if (!current() || controller.signal.aborted) throw new RequestCancelled(); throw error }
    finally { controllers.delete(controller); options.signal?.removeEventListener('abort', abort) }
  }
  return { api, cancel, capture }
}

/** 同一查询资源只允许最后一次请求生效；写操作不使用此替换机制。 */
export function createLatestRequests(api: ApiRequest) {
  const pending = new Map<string, AbortController>()
  let disposed = false
  const latest = async <T = any>(key: string, path: string, options: RequestOptions = {}): Promise<T> => {
    if (disposed) throw new RequestCancelled()
    pending.get(key)?.abort()
    const controller = new AbortController()
    pending.set(key, controller)
    const abort = () => controller.abort()
    options.signal?.addEventListener('abort', abort, { once: true })
    if (options.signal?.aborted) controller.abort()
    try {
      const result = await api<T>(path, { ...options, signal: controller.signal })
      if (pending.get(key) !== controller || controller.signal.aborted) throw new RequestCancelled()
      return result
    } finally {
      options.signal?.removeEventListener('abort', abort)
      if (pending.get(key) === controller) pending.delete(key)
    }
  }
  function cancel() { for (const controller of pending.values()) controller.abort(); pending.clear() }
  function dispose() { disposed = true; cancel() }
  return { latest, cancel, dispose }
}
