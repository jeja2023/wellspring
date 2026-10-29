import { computed, ref, type Ref } from 'vue'
import { request } from '../../shared/api/client'

type Page<T> = { items: T[]; total: number; has_more: boolean }
export type Clue = { id: string; title: string; summary: string; source: string; status: string; version: number }
type Task = { id: string; objective: string; assignee_id: string; due_date: string | null; status: string; result: string | null; version: number }
type Event = { id: string; action: string; note: string; result: string | null; actor_id: string; assignee_before_id: string | null; assignee_after_id: string | null; created_at: string }
type Person = { id: string; username: string }
type CaseChoice = { id: string; number: string; title: string }
type CaseLink = { id:string; case_number:string; case_title:string; basis:string; status:string; version:number; revoke_reason:string|null; created_by:string; revoked_by:string|null }
type Detail = { clue: Clue; task: Task | null; events: Page<Event> }
type Dependencies = { token: Ref<string>; username: Ref<string>; notice: Ref<string>; error: Ref<string>; run: (fn: () => Promise<void>) => Promise<void>; command: (name: string, path: string, data: unknown) => Promise<unknown> }

export function createIntelligence(d: Dependencies) {
  const clues=ref<Clue[]>([]), total=ref(0), page=ref(1), selected=ref<Detail|null>(null), eventPage=ref(1)
  const searchInput=ref(''), statusInput=ref(''), appliedSearch=ref(''), appliedStatus=ref('')
  const people=ref<Person[]>([])
  const caseChoices=ref<CaseChoice[]>([]), casePage=ref(1), caseTotal=ref(0), caseSearch=ref(''), caseQuery=ref(''), caseId=ref(''), linkBasis=ref('')
  const caseLinks=ref<CaseLink[]>([]), linkPage=ref(1), linkTotal=ref(0), revokeId=ref(''), revokeReason=ref('')
  const title=ref(''), summary=ref(''), source=ref(''), reviewNote=ref(''), objective=ref(''), assignee=ref('')
  const transitionNote=ref(''), result=ref('NO_FINDING'), dueDate=ref('')
  const reassigning=ref(false), reassignee=ref(''), reassignReason=ref('')
  const myTasks=ref<(Task & {clue_title:string})[]>([]), myTotal=ref(0), mineLoading=ref(false), mineError=ref('')
  const reviewTasks=ref<{id:string;clue_id:string;clue_title:string;status:string}[]>([]),reviewTotal=ref(0),reviewLoading=ref(false),reviewError=ref('')
  const actorId=computed(()=>people.value.find(x=>x.username===d.username.value)?.id)
  async function api(path:string) { return request(path,d.token.value) }
  async function loadList(targetPage=page.value, keyword=appliedSearch.value, status=appliedStatus.value) {
    const r:Page<Clue>=await request('/intelligence/clues/search',d.token.value,{method:'POST',body:JSON.stringify({keyword,status:status || null,page:targetPage,page_size:20})})
    clues.value=r.items;total.value=r.total;page.value=targetPage;appliedSearch.value=keyword;appliedStatus.value=status
  }
  async function searchClues() { await d.run(async()=>{await loadList(1,searchInput.value.trim(),statusInput.value)}) }
  async function resetClueSearch() { await d.run(async()=>{await loadList(1,'','');searchInput.value='';statusInput.value=''}) }
  async function loadCaseChoices() { const r:Page<CaseChoice>=await api(`/cases?page=${casePage.value}&page_size=20&q=${encodeURIComponent(caseQuery.value)}`);caseChoices.value=r.items;caseTotal.value=r.total }
  async function loadLinks(id:string) { const r:Page<CaseLink>=await api(`/intelligence/clues/${id}/case-links?page=${linkPage.value}&page_size=20`);caseLinks.value=r.items;linkTotal.value=r.total }
  async function searchLinkCases() { await d.run(async()=>{casePage.value=1;caseQuery.value=caseSearch.value;caseId.value='';await loadCaseChoices()}) }
  async function nextLinkCases(delta:number) { await d.run(async()=>{const previous=casePage.value;casePage.value+=delta;caseId.value='';try {await loadCaseChoices()} catch(e){casePage.value=previous;throw e}}) }
  async function nextLinks(delta:number) { if(!selected.value)return;await d.run(async()=>{const previous=linkPage.value;linkPage.value+=delta;try {await loadLinks(selected.value!.clue.id)} catch(e){linkPage.value=previous;throw e}}) }
  async function loadPeople() { people.value=await api('/intelligence/assignees') }
  async function loadDetail(id:string) { selected.value=await api(`/intelligence/clues/${id}/detail?page=${eventPage.value}&page_size=20`) }
  async function loadMine() {
    mineLoading.value=true;mineError.value=''
    try { const response:Page<Task & {clue_title:string}>=await api('/intelligence/tasks/mine?page=1&page_size=5');myTasks.value=response.items;myTotal.value=response.total }
    catch { myTasks.value=[];myTotal.value=0;mineError.value='待办加载失败，请重试。' }
    finally { mineLoading.value=false }
  }
  async function loadReviewQueue() {
    reviewLoading.value=true;reviewError.value=''
    try { const response:Page<{id:string;clue_id:string;clue_title:string;status:string}>=await api('/intelligence/tasks/reviewable?page=1&page_size=5');reviewTasks.value=response.items;reviewTotal.value=response.total }
    catch { reviewTasks.value=[];reviewTotal.value=0;reviewError.value='待复核列表加载失败，请重试。' }
    finally { reviewLoading.value=false }
  }
  async function activate() { await d.run(async()=>{await Promise.all([loadList(),loadPeople()])}) }
  async function show(id:string) { await d.run(async()=>{eventPage.value=1;linkPage.value=1;caseLinks.value=[];linkTotal.value=0;revokeId.value='';revokeReason.value='';caseId.value='';linkBasis.value='';reassigning.value=false;reassignee.value='';reassignReason.value='';await Promise.all([loadDetail(id),loadLinks(id)])}) }
  async function nextPage(delta:number) { await d.run(async()=>{await loadList(page.value+delta)}) }
  async function nextEvents(delta:number) { if(!selected.value)return;await d.run(async()=>{const previous=eventPage.value;eventPage.value+=delta;try {await loadDetail(selected.value!.clue.id)} catch(e){eventPage.value=previous;throw e}}) }
  async function refreshAfterWrite(message:string, id?:string) {
    d.notice.value=message
    try { await loadList(); if(id) await Promise.all([loadDetail(id),loadLinks(id)]) }
    catch { d.error.value='操作已成功，但页面刷新失败。请重新查看，避免重复提交。' }
  }
  async function create() { await d.run(async()=>{
    await d.command('clue-create','/intelligence/clues',{title:title.value,summary:summary.value,source:source.value})
    title.value='';summary.value='';source.value='';await refreshAfterWrite('线索草稿已创建')
  }) }
  async function review() { if(!selected.value)return; await d.run(async()=>{
    const c=selected.value!.clue
    await d.command('clue-review',`/intelligence/clues/${c.id}/review`,{version:c.version,note:reviewNote.value})
    reviewNote.value='';await refreshAfterWrite('开发验证核验已记录',c.id)
  }) }
  async function createTask() { if(!selected.value)return; await d.run(async()=>{
    const c=selected.value!.clue
    await d.command('clue-task',`/intelligence/clues/${c.id}/tasks`,{clue_version:c.version,objective:objective.value,assignee_id:assignee.value,due_date:dueDate.value || null})
    objective.value='';assignee.value='';dueDate.value='';await refreshAfterWrite('核查工单已创建',c.id)
  }) }
  async function transition(action:'SUBMIT'|'RETURN'|'CLOSE') { if(!selected.value?.task)return;await d.run(async()=>{
    const c=selected.value!.clue, task=selected.value!.task!
    const body={version:task.version,action,note:transitionNote.value,...(action==='SUBMIT'?{result:result.value}:{})}
    await d.command('clue-transition',`/intelligence/tasks/${task.id}/transition`,body)
    transitionNote.value='';await refreshAfterWrite('工单处理已记录',c.id)
  }) }
  async function reassignTask() { if(!selected.value?.task)return;await d.run(async()=>{
    const c=selected.value!.clue, task=selected.value!.task!
    await d.command('task-reassign',`/intelligence/tasks/${task.id}/reassign`,{version:task.version,assignee_id:reassignee.value,reason:reassignReason.value})
    reassigning.value=false;reassignee.value='';reassignReason.value='';await refreshAfterWrite('工单已重新分派',c.id)
  }) }
  async function createCaseLink() { if(!selected.value)return;await d.run(async()=>{
    const c=selected.value!.clue
    await d.command('clue-case-link',`/intelligence/clues/${c.id}/case-links`,{case_id:caseId.value,clue_version:c.version,basis:linkBasis.value})
    caseId.value='';linkBasis.value='';linkPage.value=1;await refreshAfterWrite('案件关联已记录',c.id)
  }) }
  async function revokeCaseLink(link:CaseLink) { if(!selected.value)return;await d.run(async()=>{
    const clueId=selected.value!.clue.id
    await d.command('clue-case-revoke',`/intelligence/case-links/${link.id}/revoke`,{version:link.version,reason:revokeReason.value})
    revokeId.value='';revokeReason.value='';await refreshAfterWrite('案件关联已撤销，历史记录保留',clueId)
  }) }
  function reset() { clues.value=[]; total.value=0;page.value=1;searchInput.value='';statusInput.value='';appliedSearch.value='';appliedStatus.value='';selected.value=null;eventPage.value=1;people.value=[];title.value='';summary.value='';source.value='';reviewNote.value='';objective.value='';assignee.value='';transitionNote.value='';result.value='NO_FINDING';dueDate.value='';reassigning.value=false;reassignee.value='';reassignReason.value='';caseChoices.value=[];casePage.value=1;caseTotal.value=0;caseSearch.value='';caseQuery.value='';caseId.value='';linkBasis.value='';caseLinks.value=[];linkPage.value=1;linkTotal.value=0;revokeId.value='';revokeReason.value='';myTasks.value=[];myTotal.value=0;mineError.value='';mineLoading.value=false;reviewTasks.value=[];reviewTotal.value=0;reviewLoading.value=false;reviewError.value='' }
  return {clues,total,page,searchInput,statusInput,appliedSearch,appliedStatus,searchClues,resetClueSearch,selected,eventPage,people,caseChoices,casePage,caseTotal,caseSearch,caseId,linkBasis,caseLinks,linkPage,linkTotal,revokeId,revokeReason,reassigning,reassignee,reassignReason,reassignTask,searchLinkCases,nextLinkCases,nextLinks,createCaseLink,revokeCaseLink,title,summary,source,reviewNote,objective,assignee,dueDate,transitionNote,result,actorId,myTasks,myTotal,mineLoading,mineError,loadMine,reviewTasks,reviewTotal,reviewLoading,reviewError,loadReviewQueue,activate,show,nextPage,nextEvents,create,review,createTask,transition,reset}
}
