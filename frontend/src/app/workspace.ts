import { computed, ref, inject, provide, watch, type InjectionKey } from 'vue'
import { ApiError, createLatestRequests, createRequestScope, isCancelled, RequestCancelled, request } from '../shared/api/client'
import { newIdempotencyKey } from '../shared/api/idempotency'
import { createIntelligence } from '../features/intelligence/controller'
import { createPersons } from '../features/persons/controller'
import type {ResourceType} from '../features/geography/types'
import type {WorkFocus,WorkModule} from '../features/dashboard/workbench'

export function createWorkspace() {
type Case = { id: string; number: string; title: string; status: string }
type Page<T> = { items: T[]; total: number; page: number; page_size: number; has_more: boolean }
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
const workbenchFocus=ref<WorkFocus|null>(null),quickCreate=ref('')
function takeWorkbenchFocus(module:WorkModule){const value=workbenchFocus.value;if(value?.module!==module)return null;workbenchFocus.value=null;return value}
function openWorkbenchTask(item:WorkFocus){
  if(!can(item.module+'.read'))return
  workbenchFocus.value={module:item.module,kind:item.kind,id:item.id,resource_id:item.resource_id,tab:item.tab,keyword:item.keyword};quickCreate.value=''
  page.value={intelligence:'情报线索',persons:'人员档案',places:'重点场所',wastewater:'污水监测'}[item.module]
}
function startWork(action:string){
  const targets:Record<string,[string,string]>={case:['案件管理','cases'],clue:['情报线索','intelligence'],person:['人员档案','persons'],place:['重点场所','places'],sample:['污水监测','wastewater']}
  const target=targets[action];if(!target||!can(target[1]+'.read')||!can(target[1]+'.write'))return
  workbenchFocus.value=null;quickCreate.value=action;page.value=target[0]
}
const geographyFocus=ref<{type:ResourceType;id:string}|null>(null),placeFocus=ref('')
function openMap(type:ResourceType,id:string){geographyFocus.value={type,id};page.value='业务地图'}
function openPlace(id:string){placeFocus.value=id;page.value='重点场所'}
const activeRuns = ref(new Set<symbol>())
const loading = computed(() => activeRuns.value.size > 0)
const requests = createRequestScope(() => token.value || stored(sessionKey), handleUnauthorized)
const api = requests.api
const queries = createLatestRequests(api)
watch(token, () => requests.cancel(), { flush: 'sync' })
const cases = ref<Case[]>([])
const search=ref(''),caseQuery=ref(''),casePage=ref(1),caseTotal=ref(0),caseNumber=ref(''),caseTitle=ref('')
const pendingKeys = new Map<string, { key: string; path: string; body: string }>()
const menuGroups=computed(()=>[
  {label:'综合总览',items:[
    '工作台',
    ...(can('dashboard.read')?['数据大屏']:[]),
    ...(can('geography.read')?['业务地图']:[]),
  ]},
  {label:'业务办理',items:(
    [['接警信息','intake.read'],['案件管理','cases.read'],['情报线索','intelligence.read'],
     ['人员档案','persons.read'],['重点场所','places.read'],['污水监测','wastewater.read']] as const
  ).filter(([,permission])=>can(permission)).map(([name])=>name)},
  {label:'分析研判',items:[
    ...(can('ai.read')?['智能研判']:[]),
    ...(['modeling.read','models.read','tactics.read'].some(can)?['分析建模']:[]),
  ]},
  {label:'管理审计',items:[
    ...(isAdmin.value?['组织管理']:[]),
    ...(can('system.users')?['用户管理']:[]),
    ...(isAdmin.value?['角色管理','权限管理']:[]),
    ...(can('audit.read')?['操作记录']:[]),
    ...(isAdmin.value?['系统日志']:[]),
  ]},
].filter(group=>group.items.length))
const menu=computed(()=>menuGroups.value.flatMap(group=>group.items))
watch(page, value => { if (token.value && menu.value.includes(value)) save(pageKey,value) })
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
async function refresh() { await Promise.all([...(can('cases.read')?[loadCases()]:[])]) }
async function refreshAfterWrite(message: string) {
  notice.value = message
  try {
    await refresh()
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
async function searchCases() { await run(async()=>{await loadCases(1, search.value.trim())}) }
async function moveCase(delta: number) { await run(async()=>{await loadCases(casePage.value+delta)}) }
function clearSession() {
  requests.cancel(); queries.cancel(); activeRuns.value.clear(); error.value=''; notice.value=''
  remove(sessionKey); remove(pageKey); remove(legacyPageKey)
  token.value=''; username.value=''; password.value=''; organization.value=''; isAdmin.value=false; page.value='工作台'
  permissions.value=null;roleName.value='';geographyFocus.value=null;placeFocus.value=''
  workbenchFocus.value=null;quickCreate.value=''
  cases.value=[]
  search.value=''; caseQuery.value=''; casePage.value=1; caseTotal.value=0
  caseNumber.value='';caseTitle.value='';pendingKeys.clear();intelligence.reset();persons.reset()
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
    const savedPage = ['数据建模','模型管理','技战法库'].includes(oldPage)?'分析建模':['智能解析','模型服务'].includes(oldPage)?'智能研判':oldPage==='数据导入'?'案件管理':oldPage === '污水毒情监测' ? '污水监测' : ['权限审计', '我的操作记录'].includes(oldPage) ? '操作记录' : oldPage
    page.value = menu.value.includes(savedPage) ? savedPage : '工作台'
    save(pageKey, page.value); remove(legacyPageKey)
  } catch (e) {
    if (!isCancelled(e) && !(e instanceof ApiError && e.status === 401)) restoreError.value = '无法连接服务器，无法确认登录状态。请重试。'
  } finally { restoring.value = false }
}
async function login() { await run(async()=>{ const result=await api('/login',{method:'POST',body:JSON.stringify({username:username.value,password:password.value})}); token.value=result.token; username.value=result.username; organization.value=result.organization; applyIdentity(result); password.value=''; save(sessionKey,result.token); save(pageKey,'工作台'); }) }
async function logout() {
  const previousToken = token.value || stored(sessionKey)
  clearSession()
  const current = requests.capture()
  try { await request('/logout', previousToken, {method:'POST'}) }
  catch (e) {
    if (current() && !(e instanceof ApiError && e.status === 401)) error.value = '本机登录信息已清除，但服务端退出结果未确认。'
  }
}
async function makeCase() { let saved=false;await run(async()=>{ const current=requests.capture(); await command('case','/cases',{number:caseNumber.value,title:caseTitle.value}); if(!current())return;saved=true; caseNumber.value='';caseTitle.value=''; await refreshAfterWrite('案件记录已创建') });return saved }
const intelligence = createIntelligence({api, can, captureSession:requests.capture, username, notice, error, run, command})
const persons = createPersons({api,captureSession:requests.capture,notice,error,run,command})
async function openCase(number:string) {search.value=number;caseQuery.value=number;casePage.value=1;page.value='案件管理';await run(()=>loadCases(1,number))}
const filteredCases = computed(()=>cases.value)
return {workbenchFocus,quickCreate,takeWorkbenchFocus,openWorkbenchTask,startWork,geographyFocus,placeFocus,openMap,openPlace,intelligence,persons,api,captureSession:requests.capture,command,run,openCase,can,permissions,roleName,refreshCases:()=>run(()=>loadCases()),token,username,password,organization,isAdmin,restoring,restoreError,restoreSession,page,error,notice,loading,cases,search,caseQuery,casePage,caseTotal,caseNumber,caseTitle,menu,menuGroups,filteredCases,login,logout,makeCase,searchCases,moveCase}
}

type Workspace = ReturnType<typeof createWorkspace>
const key: InjectionKey<Workspace> = Symbol('workspace')
export function provideWorkspace(workspace: Workspace) { provide(key, workspace) }
export function useWorkspace(): Workspace {
  const workspace = inject(key)
  if (!workspace) throw new Error('工作区尚未初始化')
  return workspace
}
