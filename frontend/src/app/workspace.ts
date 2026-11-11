import { computed, ref, inject, provide, watch, type InjectionKey } from 'vue'
import { ApiError, createLatestRequests, createRequestScope, isCancelled, RequestCancelled, request } from '../shared/api/client'
import { newIdempotencyKey } from '../shared/api/idempotency'
import { createIntelligence } from '../features/intelligence/controller'
import { createInventory } from '../features/evidence/inventory'
import { createPersons } from '../features/persons/controller'

export function createWorkspace() {
type Case = { id: string; number: string; title: string; status: string }
type Evidence = { id: string; case_id: string; parent_id: string | null; label: string; balance: string; version: number }
type Page<T> = { items: T[]; total: number; page: number; page_size: number; has_more: boolean }
type Event = { id: string; kind: string; delta: string; reason: string; created_at: string }
const token = ref(''), username = ref(''), password = ref(''), organization = ref('')
const isAdmin = ref(false)
const permissions=ref<string[]|null>(null),roleName=ref('')
function can(code:string){return isAdmin.value||(permissions.value===null?!code.startsWith('system.'):permissions.value.includes(code))}
function applyIdentity(result:any){isAdmin.value=result.is_admin===true;permissions.value=Array.isArray(result.permissions)?result.permissions:null;roleName.value=result.role_name||''}
const restoring = ref(Boolean(stored('wellspring.session'))), restoreError = ref('')
const sessionKey = 'wellspring.session', pageKey = 'wellspring.page.v2', legacyPageKey = 'wellspring.page'
function storage() { try { return globalThis.sessionStorage } catch { return undefined } }
function stored(key:string) { try { return storage()?.getItem(key) ?? '' } catch { return '' } }
function save(key:string, value:string) { try { storage()?.setItem(key,value) } catch { /* 页面仍可在本次加载期间使用 */ } }
function remove(key:string) { try { storage()?.removeItem(key) } catch { /* 浏览器可能禁用存储 */ } }
const page = ref('工作台'), error = ref(''), notice = ref('')
const activeRuns = ref(new Set<symbol>())
const loading = computed(() => activeRuns.value.size > 0)
const requests = createRequestScope(() => token.value || stored(sessionKey), handleUnauthorized)
const api = requests.api
const queries = createLatestRequests(api)
watch(token, () => requests.cancel(), { flush: 'sync' })
const cases = ref<Case[]>([]), evidence = ref<Evidence[]>([]), events = ref<Event[]>([]), selected = ref('')
const search = ref(''), caseQuery = ref(''), casePage = ref(1), caseTotal = ref(0), evidencePage = ref(1), evidenceTotal = ref(0), eventPage = ref(1), eventTotal = ref(0), caseNumber = ref(''), caseTitle = ref('')
const evidenceCase = ref(''), label = ref(''), weight = ref(''), reason = ref('')
const sampleLabel = ref(''), sampleWeight = ref(''), sampleReason = ref('')
const pendingKeys = new Map<string, { key: string; path: string; body: string }>()
const menu=computed(()=>[
  '工作台',
  ...([['接警信息','intake.read'],['案件管理','cases.read'],['证物管理','evidence.read'],['情报线索','intelligence.read'],['污水监测','wastewater.read'],['人员档案','persons.read']] as const)
    .filter(([,permission])=>can(permission)).map(([name])=>name),
  '智能解析',
  ...(can('audit.read')?['操作记录']:[]),
  ...(can('system.users')?['用户管理']:[]),
  ...(isAdmin.value?['角色管理','权限管理','组织管理','系统日志']:[]),
])
watch(page, value => { if (token.value && menu.value.includes(value)) save(pageKey,value) })
const selectedItem = computed(() => evidence.value.find(x => x.id === selected.value))
async function run(fn: () => Promise<void>) {
  const current = requests.capture(), id = Symbol('operation')
  activeRuns.value.add(id); error.value = ''; notice.value = ''
  try { await fn() }
  catch (e) { if (current() && !isCancelled(e)) error.value = e instanceof Error ? e.message : '请求失败' }
  finally { activeRuns.value.delete(id) }
}
async function loadCases(target = casePage.value, query = caseQuery.value) {
  const current = requests.capture()
  const result = await queries.latest<Page<Case>>('cases', `/cases?page=${target}&page_size=20&q=${encodeURIComponent(query)}`)
  if (!current()) throw new RequestCancelled()
  cases.value = result.items; caseTotal.value = result.total; casePage.value = target; caseQuery.value = query
}
async function loadEvidence(target = evidencePage.value) {
  const current = requests.capture()
  const result = await queries.latest<Page<Evidence>>('evidence', `/evidence?page=${target}&page_size=20`)
  if (!current()) throw new RequestCancelled()
  evidence.value = result.items; evidenceTotal.value = result.total; evidencePage.value = target
}
async function loadEvents(id = selected.value, target = eventPage.value) {
  const current = requests.capture()
  if (!id) return
  const result = await queries.latest<Page<Event>>('events', `/evidence/${id}/events?page=${target}&page_size=20`)
  if (!current()) throw new RequestCancelled()
  if (selected.value !== id) return
  events.value = result.items; eventTotal.value = result.total; eventPage.value = target
}
async function refresh() { await Promise.all([...(can('cases.read')?[loadCases()]:[]),...(can('evidence.read')?[loadEvidence()]:[])]) }
async function refreshAfterWrite(message: string, includeEvents = false) {
  notice.value = message
  try {
    await refresh()
    if (includeEvents) await loadEvents()
  } catch (e) {
    if (isCancelled(e)) throw e
    error.value = '操作已成功，但列表刷新失败。请重新查询，避免重复提交。'
  }
}
async function command(name: string, path: string, data: unknown) {
  const current = requests.capture()
  const body = JSON.stringify(data)
  const old = pendingKeys.get(name)
  if (old && (old.body !== body || old.path !== path)) throw new Error('上次请求结果尚未确认，请恢复原输入并重试或重新登录后核查记录')
  const entry = old ?? {key: newIdempotencyKey(),path,body}
  pendingKeys.set(name,entry)
  try {
    const response = await api(path,{method:'POST',headers:{'Idempotency-Key':entry.key},body})
    if (!current()) throw new RequestCancelled()
    pendingKeys.delete(name)
    return response
  } catch (e) {
    if (current() && e instanceof ApiError && e.definitive) pendingKeys.delete(name)
    throw e
  }
}
async function searchCases() { await run(async()=>{await loadCases(1, search.value.trim());evidenceCase.value=''}) }
async function moveCase(delta: number) { await run(async()=>{await loadCases(casePage.value+delta);evidenceCase.value=''}) }
async function moveEvidence(delta: number) { await run(async()=>{await loadEvidence(evidencePage.value+delta);selected.value='';events.value=[];eventTotal.value=0;inventory.reset()}) }
async function moveEvents(delta: number) { await run(async()=>{await loadEvents(selected.value,eventPage.value+delta)}) }
function clearSession() {
  requests.cancel(); queries.cancel(); activeRuns.value.clear(); error.value=''; notice.value=''
  remove(sessionKey); remove(pageKey); remove(legacyPageKey)
  token.value=''; username.value=''; password.value=''; organization.value=''; isAdmin.value=false; page.value='工作台'
  permissions.value=null;roleName.value=''
  cases.value=[]; evidence.value=[]; events.value=[]; selected.value=''
  search.value=''; caseQuery.value=''; casePage.value=1; caseTotal.value=0
  evidencePage.value=1; evidenceTotal.value=0; eventPage.value=1; eventTotal.value=0
  caseNumber.value=''; caseTitle.value=''; evidenceCase.value=''; label.value=''; weight.value=''; reason.value=''
  sampleLabel.value=''; sampleWeight.value=''; sampleReason.value=''; pendingKeys.clear(); intelligence.reset(); inventory.reset(); persons.reset()
}
function handleUnauthorized(expiredToken: string) {
  if (expiredToken && (token.value === expiredToken || (!token.value && stored(sessionKey) === expiredToken))) {
    clearSession(); restoreError.value = ''; error.value = '登录已失效，请重新登录。'
  }
}
async function restoreSession() {
  const savedToken = stored(sessionKey)
  if (!savedToken) return
  restoring.value = true; restoreError.value = ''
  try {
    const result = await api('/session')
    token.value = savedToken; username.value = result.username; organization.value = result.organization; applyIdentity(result)
    const legacyPage = stored(legacyPageKey)
    const oldPage = stored(pageKey) || (legacyPage === '案件管理' ? '接警信息' : legacyPage === '业务案件' ? '案件管理' : legacyPage)
    const savedPage = oldPage==='数据导入'?'案件管理':oldPage === '污水毒情监测' ? '污水监测' : ['权限审计', '我的操作记录'].includes(oldPage) ? '操作记录' : oldPage
    page.value = menu.value.includes(savedPage) ? savedPage : '工作台'
    save(pageKey, page.value); remove(legacyPageKey)
    try { await refresh() } catch (e) { if (isCancelled(e)) return; error.value = '登录已恢复，但数据加载失败，请重新查询。' }
  } catch (e) {
    if (!isCancelled(e) && !(e instanceof ApiError && e.status === 401)) restoreError.value = '无法连接服务器，无法确认登录状态。请重试。'
  } finally { restoring.value = false }
}
async function login() { await run(async()=>{ const result=await api('/login',{method:'POST',body:JSON.stringify({username:username.value,password:password.value})}); token.value=result.token; username.value=result.username; organization.value=result.organization; applyIdentity(result); password.value=''; save(sessionKey,result.token); save(pageKey,'工作台'); try { await refresh() } catch (e) { if (!isCancelled(e)) error.value = '登录成功，但数据加载失败，请重新查询。' } }) }
async function logout() {
  const previousToken = token.value || stored(sessionKey)
  clearSession()
  const current = requests.capture()
  try { await request('/logout', previousToken, {method:'POST'}) }
  catch (e) {
    if (current() && !(e instanceof ApiError && e.status === 401)) error.value = '本机登录信息已清除，但服务端退出结果未确认。'
  }
}
async function makeCase() { let saved=false;await run(async()=>{ const current=requests.capture(); await command('case','/cases',{number:caseNumber.value,title:caseTitle.value}); if(!current())return;saved=true; caseNumber.value='';caseTitle.value=''; await refreshAfterWrite('案件草稿已创建') });return saved }
async function makeEvidence() { let saved=false;await run(async()=>{ const current=requests.capture(); await command('evidence','/evidence',{case_id:evidenceCase.value,label:label.value,weight:weight.value,reason:reason.value}); if(!current())return;saved=true; label.value='';weight.value='';reason.value='';await refreshAfterWrite('证物和初始重量流水已登记') });return saved }
async function viewEvents(id:string) { await run(async()=>{selected.value=id;eventPage.value=1;events.value=[];inventory.reset();await Promise.all([loadEvents(id,1),inventory.load(id,1)])}) }
async function makeSample() { await run(async()=>{const current=requests.capture();await command('sample',`/evidence/${selected.value}/samples`,{label:sampleLabel.value,weight:sampleWeight.value,reason:sampleReason.value,source_version:selectedItem.value?.version});if(!current())return;sampleLabel.value='';sampleWeight.value='';sampleReason.value='';await refreshAfterWrite('分样流水已记录', true)}) }
const intelligence = createIntelligence({api, can, captureSession:requests.capture, username, notice, error, run, command})
const inventory = createInventory({api,captureSession:requests.capture,selected,selectedItem,notice,error,run,command,refreshEvidence:loadEvidence})
const persons = createPersons({api,captureSession:requests.capture,notice,error,run,command})
async function openCase(number:string) {search.value=number;caseQuery.value=number;casePage.value=1;page.value='案件管理';await run(()=>loadCases(1,number))}
const filteredCases = computed(()=>cases.value)
return { intelligence, inventory, persons, api, captureSession:requests.capture, command, run, openCase, can, permissions, roleName, refreshCases:()=>run(()=>loadCases()), refreshEvidence:loadEvidence, token, username, password, organization, isAdmin, restoring, restoreError, restoreSession, page, error, notice, loading, cases, evidence, events, selected, search, caseQuery, casePage, caseTotal, evidencePage, evidenceTotal, eventPage, eventTotal, caseNumber, caseTitle, evidenceCase, label, weight, reason, sampleLabel, sampleWeight, sampleReason, menu, selectedItem, filteredCases, login, logout, makeCase, makeEvidence, viewEvents, makeSample, searchCases, moveCase, moveEvidence, moveEvents }
}

type Workspace = ReturnType<typeof createWorkspace>
const key: InjectionKey<Workspace> = Symbol('workspace')
export function provideWorkspace(workspace: Workspace) { provide(key, workspace) }
export function useWorkspace(): Workspace {
  const workspace = inject(key)
  if (!workspace) throw new Error('工作区尚未初始化')
  return workspace
}
