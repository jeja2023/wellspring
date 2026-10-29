export class ApiError extends Error {
  constructor(message: string, public definitive: boolean) { super(message) }
}

export async function request(path: string, token: string, options: RequestInit = {}) {
  const headers = new Headers(options.headers)
  headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  let response: Response
  try {
    response = await fetch(`/api${path}`, { ...options, headers })
  } catch {
    throw new ApiError('网络中断，操作结果尚未确认；请保留当前输入并重试。', false)
  }
  let data: any
  try { data = await response.json() }
  catch { throw new ApiError('服务返回异常，操作结果尚未确认；请保留当前输入并重试。', false) }
  if (!response.ok) {
    const message = typeof data?.message === 'string' ? data.message : '请求失败，请检查输入'
    throw new ApiError(message, response.status < 500 && data?.code !== 'IDEMPOTENCY_IN_PROGRESS')
  }
  return data
}
