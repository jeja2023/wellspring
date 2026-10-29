import { computed, ref, inject, provide, type InjectionKey } from 'vue'
import { ApiError, request } from '../shared/api/client'
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
const page = ref('工作台'), error = ref(''), notice = ref(''), loading = ref(false)
const cases = ref<Case[]>([]), evidence = ref<Evidence[]>([]), events = ref<Event[]>([]), selected = ref('')
const search = ref(''), caseQuery = ref(''), casePage = ref(1), caseTotal = ref(0), evidencePage = ref(1), evidenceTotal = ref(0), eventPage = ref(1), eventTotal = ref(0), caseNumber = ref(''), caseTitle = ref('')
const evidenceCase = ref(''), label = ref(''), weight = ref(''), reason = ref('')
const sampleLabel = ref(''), sampleWeight = ref(''), sampleReason = ref('')
const pendingKeys = new Map<string, { key: string; path: string; body: string }>()
const menu = ['工作台','案件管理','证物管理','情报线索','人员档案','数据导入','权限与审计','AI 文书解析']
const selectedItem = computed(() => evidence.value.find(x => x.id === selected.value))
async function api(path: string, options: RequestInit = {}) { return request(path, token.value, options) }
async function run(fn: () => Promise<void>) { error.value=''; notice.value=''; loading.value=true; try { await fn() } catch(e) { error.value = e instanceof Error ? e.message : '请求失败' } finally { loading.value=false } }
async function loadCases() { const result: Page<Case> = await api(`/cases?page=${casePage.value}&page_size=20&q=${encodeURIComponent(caseQuery.value)}`); cases.value=result.items;caseTotal.value=result.total }
async function loadEvidence() { const result: Page<Evidence> = await api(`/evidence?page=${evidencePage.value}&page_size=20`);evidence.value=result.items;evidenceTotal.value=result.total }
async function loadEvents() { const result: Page<Event> = await api(`/evidence/${selected.value}/events?page=${eventPage.value}&page_size=20`);events.value=result.items;eventTotal.value=result.total }
async function refresh() { await Promise.all([loadCases(),loadEvidence()]) }
async function refreshAfterWrite(message: string, includeEvents = false) {
  notice.value = message
  try {
    await refresh()
    if (includeEvents) await loadEvents()
  } catch {
    error.value = '操作已成功，但列表刷新失败。请重新查询，避免重复提交。'
  }
}
async function command(name: string, path: string, data: unknown) {
  const body = JSON.stringify(data)
  const old = pendingKeys.get(name)
  if (old && (old.body !== body || old.path !== path)) throw new Error('上次请求结果尚未确认，请恢复原输入并重试或重新登录后核查记录')
  const entry = old ?? {key: newIdempotencyKey(),path,body}
  pendingKeys.set(name,entry)
  try {
    const response = await api(path,{method:'POST',headers:{'Idempotency-Key':entry.key},body})
    pendingKeys.delete(name)
    return response
  } catch (e) {
    if (e instanceof ApiError && e.definitive) pendingKeys.delete(name)
    throw e
  }
}
async function searchCases() { await run(async()=>{casePage.value=1;caseQuery.value=search.value;evidenceCase.value='';await loadCases()}) }
async function moveCase(delta: number) { await run(async()=>{casePage.value+=delta;evidenceCase.value='';await loadCases()}) }
async function moveEvidence(delta: number) { await run(async()=>{evidencePage.value+=delta;selected.value='';events.value=[];inventory.reset();await loadEvidence()}) }
async function moveEvents(delta: number) { await run(async()=>{eventPage.value+=delta;await loadEvents()}) }
async function login() { await run(async()=>{ const result=await api('/login',{method:'POST',body:JSON.stringify({username:username.value,password:password.value})}); token.value=result.token; organization.value=result.organization; password.value=''; await refresh() }) }
async function logout() { await run(async()=>{
  await api('/logout',{method:'POST'})
  token.value=''; username.value=''; password.value=''; organization.value=''; page.value='工作台'
  cases.value=[]; evidence.value=[]; events.value=[]; selected.value=''
  search.value=''; caseQuery.value=''; casePage.value=1; caseTotal.value=0
  evidencePage.value=1; evidenceTotal.value=0; eventPage.value=1; eventTotal.value=0
  caseNumber.value=''; caseTitle.value=''; evidenceCase.value=''; label.value=''; weight.value=''; reason.value=''
  sampleLabel.value=''; sampleWeight.value=''; sampleReason.value=''; pendingKeys.clear(); intelligence.reset(); inventory.reset(); persons.reset()
}) }
async function makeCase() { await run(async()=>{ await command('case','/cases',{number:caseNumber.value,title:caseTitle.value}); caseNumber.value='';caseTitle.value=''; await refreshAfterWrite('案件草稿已创建') }) }
async function makeEvidence() { await run(async()=>{ await command('evidence','/evidence',{case_id:evidenceCase.value,label:label.value,weight:weight.value,reason:reason.value}); label.value='';weight.value='';reason.value='';await refreshAfterWrite('证物和初始重量流水已登记') }) }
async function viewEvents(id:string) { await run(async()=>{selected.value=id;eventPage.value=1;events.value=[];inventory.reset();await Promise.all([loadEvents(),inventory.load(id,1)])}) }
async function makeSample() { await run(async()=>{await command('sample',`/evidence/${selected.value}/samples`,{label:sampleLabel.value,weight:sampleWeight.value,reason:sampleReason.value,source_version:selectedItem.value?.version});sampleLabel.value='';sampleWeight.value='';sampleReason.value='';await refreshAfterWrite('分样流水已记录', true)}) }
const intelligence = createIntelligence({token, username, notice, error, run, command})
const inventory = createInventory({token,selected,selectedItem,notice,error,run,command,refreshEvidence:loadEvidence})
const persons = createPersons({token,notice,error,run,command})
const filteredCases = computed(()=>cases.value)
return { intelligence, inventory, persons, command, run, token, username, password, organization, page, error, notice, loading, cases, evidence, events, selected, search, caseQuery, casePage, caseTotal, evidencePage, evidenceTotal, eventPage, eventTotal, caseNumber, caseTitle, evidenceCase, label, weight, reason, sampleLabel, sampleWeight, sampleReason, menu, selectedItem, filteredCases, login, logout, makeCase, makeEvidence, viewEvents, makeSample, searchCases, moveCase, moveEvidence, moveEvents }
}

type Workspace = ReturnType<typeof createWorkspace>
const key: InjectionKey<Workspace> = Symbol('workspace')
export function provideWorkspace(workspace: Workspace) { provide(key, workspace) }
export function useWorkspace(): Workspace {
  const workspace = inject(key)
  if (!workspace) throw new Error('工作区尚未初始化')
  return workspace
}
