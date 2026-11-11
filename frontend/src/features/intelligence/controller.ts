import { computed, ref, type Ref } from 'vue'
import { createLatestRequests, isCancelled, RequestCancelled, type ApiRequest } from '../../shared/api/client'

type Page<T> = { items: T[]; total: number; has_more: boolean }
export type Clue = { reference_no?:string|null;priority?:string;suggested_due_date?:string|null;id: string; title: string; summary: string; source: string; status: string; version: number }
type Task = { id: string; objective: string; assignee_id: string; due_date: string | null; status: string; result: string | null; version: number }
type Event = { id: string; action: string; note: string; result: string | null; actor_id: string; assignee_before_id: string | null; assignee_after_id: string | null; created_at: string }
type Person = { id: string; username: string }
type CaseChoice = { id: string; number: string; title: string }
type CaseLink = { id:string; case_number:string; case_title:string; basis:string; status:string; version:number; revoke_reason:string|null; created_by:string; revoked_by:string|null }
type Detail = { clue: Clue; task: Task | null; events: Page<Event> }
type Dependencies = { api: ApiRequest; can?:(code:string)=>boolean; captureSession:()=>()=>boolean; username: Ref<string>; notice: Ref<string>; error: Ref<string>; run: (fn: () => Promise<void>) => Promise<void>; command: (name: string, path: string, data: unknown) => Promise<unknown> }

export function createIntelligence(d: Dependencies) {
  const queries = createLatestRequests(d.api)
  const clues=ref<Clue[]>([]), total=ref(0), page=ref(1), selected=ref<Detail|null>(null), eventPage=ref(1)
  const searchInput=ref(''), statusInput=ref(''), appliedSearch=ref(''), appliedStatus=ref('')
  const people=ref<Person[]>([])
  const caseChoices=ref<CaseChoice[]>([]), casePage=ref(1), caseTotal=ref(0), caseSearch=ref(''), caseQuery=ref(''), caseId=ref(''), linkBasis=ref('')
  const caseLinks=ref<CaseLink[]>([]), linkPage=ref(1), linkTotal=ref(0), revokeId=ref(''), revokeReason=ref('')
  const referenceNo=ref(''),priority=ref('NORMAL'),suggestedDueDate=ref('')
  const title=ref(''), summary=ref(''), source=ref(''), reviewNote=ref(''), objective=ref(''), assignee=ref('')
  const transitionNote=ref(''), result=ref('NO_FINDING'), dueDate=ref('')
  const reassigning=ref(false), reassignee=ref(''), reassignReason=ref('')
  const myTasks=ref<(Task & {clue_title:string})[]>([]), myTotal=ref(0), mineLoading=ref(false), mineError=ref('')
  const reviewTasks=ref<{id:string;clue_id:string;clue_title:string;status:string}[]>([]),reviewTotal=ref(0),reviewLoading=ref(false),reviewError=ref('')
  const myPage=ref(1),reviewPage=ref(1)
  let mineSequence=0, reviewSequence=0
  const actorId=computed(()=>people.value.find(x=>x.username===d.username.value)?.id)
  async function api(path:string, key=path.split('?')[0]) { return queries.latest(key,path) }
  async function loadList(targetPage=page.value, keyword=appliedSearch.value, status=appliedStatus.value) { const current=d.captureSession();
    const r:Page<Clue>=await queries.latest('list','/intelligence/clues/search',{method:'POST',body:JSON.stringify({keyword,status:status || null,page:targetPage,page_size:20})}); if(!current())throw new RequestCancelled()
    clues.value=r.items;total.value=r.total;page.value=targetPage;appliedSearch.value=keyword;appliedStatus.value=status
  }
  async function searchClues() { await d.run(async()=>{await loadList(1,searchInput.value.trim(),statusInput.value)}) }
  async function resetClueSearch() { await d.run(async()=>{await loadList(1,'','');searchInput.value='';statusInput.value=''}) }
  async function loadCaseChoices(target=casePage.value, query=caseQuery.value) { const current=d.captureSession(); const r:Page<CaseChoice>=await api(`/cases?page=${target}&page_size=20&q=${encodeURIComponent(query)}`); if(!current())throw new RequestCancelled();caseChoices.value=r.items;caseTotal.value=r.total;casePage.value=target;caseQuery.value=query }
  async function loadLinks(id:string,target=linkPage.value) { const current=d.captureSession(); const r:Page<CaseLink>=await api(`/intelligence/clues/${id}/case-links?page=${target}&page_size=20`,'links'); if(!current())throw new RequestCancelled();caseLinks.value=r.items;linkTotal.value=r.total;linkPage.value=target }
  async function searchLinkCases() { await d.run(async()=>{await loadCaseChoices(1,caseSearch.value.trim());caseId.value=''}) }
  async function nextLinkCases(delta:number) { await d.run(async()=>{await loadCaseChoices(casePage.value+delta);caseId.value=''}) }
  async function nextLinks(delta:number) { if(!selected.value)return;await d.run(async()=>{await loadLinks(selected.value!.clue.id,linkPage.value+delta)}) }
  async function loadPeople() { const current=d.captureSession(); const value=await api('/intelligence/assignees');if(!current())throw new RequestCancelled();people.value=value }
  async function loadDetail(id:string,target=eventPage.value) { const current=d.captureSession(); const value=await api(`/intelligence/clues/${id}/detail?page=${target}&page_size=20`,'detail');if(!current())throw new RequestCancelled();selected.value=value;eventPage.value=target }
  async function loadMine(targetPage=myPage.value) { const current=d.captureSession(), sequence=++mineSequence;
    mineLoading.value=true;mineError.value=''
    try { const response:Page<Task & {clue_title:string}>=await api(`/intelligence/tasks/mine?page=${targetPage}&page_size=5`); if(!current())throw new RequestCancelled();myTasks.value=response.items;myTotal.value=response.total;myPage.value=targetPage }
    catch (e) { if (isCancelled(e)) return; myPage.value=1;myTasks.value=[];myTotal.value=0;mineError.value='待办加载失败，请重试。' }
    finally { if(current() && sequence===mineSequence) mineLoading.value=false }
  }
  async function loadReviewQueue(targetPage=reviewPage.value) { const current=d.captureSession(), sequence=++reviewSequence;
    reviewLoading.value=true;reviewError.value=''
    try { const response:Page<{id:string;clue_id:string;clue_title:string;status:string}>=await api(`/intelligence/tasks/reviewable?page=${targetPage}&page_size=5`); if(!current())throw new RequestCancelled();reviewTasks.value=response.items;reviewTotal.value=response.total;reviewPage.value=targetPage }
    catch (e) { if (isCancelled(e)) return; reviewPage.value=1;reviewTasks.value=[];reviewTotal.value=0;reviewError.value='待复核列表加载失败，请重试。' }
    finally { if(current() && sequence===reviewSequence) reviewLoading.value=false }
  }
  async function activate() { await d.run(async()=>{await Promise.all([loadList(),loadPeople()])}) }
  async function show(id:string) { await d.run(async()=>{selected.value=null;eventPage.value=1;linkPage.value=1;caseLinks.value=[];linkTotal.value=0;revokeId.value='';revokeReason.value='';caseId.value='';linkBasis.value='';reassigning.value=false;reassignee.value='';reassignReason.value='';await Promise.all([loadDetail(id),...(d.can?.('cases.read')===false?[]:[loadLinks(id)])])}) }
  async function nextPage(delta:number) { await d.run(async()=>{await loadList(page.value+delta)}) }
  async function nextEvents(delta:number) { if(!selected.value)return;await d.run(async()=>{await loadDetail(selected.value!.clue.id,eventPage.value+delta)}) }
  async function refreshAfterWrite(message:string, id?:string) {
    d.notice.value=message
    try { await loadList(); if(id) await Promise.all([loadDetail(id),...(d.can?.('cases.read')===false?[]:[loadLinks(id)])]) }
    catch (e) { if (isCancelled(e)) throw e; d.error.value='操作已成功，但页面刷新失败。请重新查看，避免重复提交。' }
  }
  async function create() { let saved=false;await d.run(async()=>{
    const current=d.captureSession()
    await d.command('clue-create','/intelligence/clues',{title:title.value,summary:summary.value,source:source.value,...(referenceNo.value?{reference_no:referenceNo.value}:{}),...(priority.value!=='NORMAL'?{priority:priority.value}:{}),...(suggestedDueDate.value?{suggested_due_date:suggestedDueDate.value}:{})})
    if (!current()) throw new RequestCancelled()
    saved=true
    title.value='';summary.value='';source.value='';referenceNo.value='';priority.value='NORMAL';suggestedDueDate.value='';await refreshAfterWrite('线索草稿已创建')
  });return saved }
  async function review() { if(!selected.value)return; await d.run(async()=>{
    const c=selected.value!.clue
    const current=d.captureSession()
    await d.command('clue-review',`/intelligence/clues/${c.id}/review`,{version:c.version,note:reviewNote.value})
    if (!current()) throw new RequestCancelled()
    reviewNote.value='';await refreshAfterWrite('开发验证核验已记录',c.id)
  }) }
  async function createTask() { if(!selected.value)return; await d.run(async()=>{
    const c=selected.value!.clue
    const current=d.captureSession()
    await d.command('clue-task',`/intelligence/clues/${c.id}/tasks`,{clue_version:c.version,objective:objective.value,assignee_id:assignee.value,due_date:dueDate.value || null})
    if (!current()) throw new RequestCancelled()
    objective.value='';assignee.value='';dueDate.value='';await refreshAfterWrite('核查工单已创建',c.id)
  }) }
  async function transition(action:'SUBMIT'|'RETURN'|'CLOSE') { if(!selected.value?.task)return;await d.run(async()=>{
    const c=selected.value!.clue, task=selected.value!.task!
    const body={version:task.version,action,note:transitionNote.value,...(action==='SUBMIT'?{result:result.value}:{})}
    const current=d.captureSession()
    await d.command('clue-transition',`/intelligence/tasks/${task.id}/transition`,body)
    if (!current()) throw new RequestCancelled()
    transitionNote.value='';await refreshAfterWrite('工单处理已记录',c.id)
  }) }
  async function reassignTask() { if(!selected.value?.task)return;await d.run(async()=>{
    const c=selected.value!.clue, task=selected.value!.task!
    const current=d.captureSession()
    await d.command('task-reassign',`/intelligence/tasks/${task.id}/reassign`,{version:task.version,assignee_id:reassignee.value,reason:reassignReason.value})
    if (!current()) throw new RequestCancelled()
    reassigning.value=false;reassignee.value='';reassignReason.value='';await refreshAfterWrite('工单已重新分派',c.id)
  }) }
  async function createCaseLink() { if(!selected.value)return;await d.run(async()=>{
    const c=selected.value!.clue
    const current=d.captureSession()
    await d.command('clue-case-link',`/intelligence/clues/${c.id}/case-links`,{case_id:caseId.value,clue_version:c.version,basis:linkBasis.value})
    if (!current()) throw new RequestCancelled()
    caseId.value='';linkBasis.value='';linkPage.value=1;await refreshAfterWrite('案件关联已记录',c.id)
  }) }
  async function revokeCaseLink(link:CaseLink) { if(!selected.value)return;await d.run(async()=>{
    const clueId=selected.value!.clue.id
    const current=d.captureSession()
    await d.command('clue-case-revoke',`/intelligence/case-links/${link.id}/revoke`,{version:link.version,reason:revokeReason.value})
    if (!current()) throw new RequestCancelled()
    revokeId.value='';revokeReason.value='';await refreshAfterWrite('案件关联已撤销，历史记录保留',clueId)
  }) }
  function reset() { referenceNo.value='';priority.value='NORMAL';suggestedDueDate.value='';queries.cancel();mineSequence++;reviewSequence++; clues.value=[]; total.value=0;page.value=1;searchInput.value='';statusInput.value='';appliedSearch.value='';appliedStatus.value='';selected.value=null;eventPage.value=1;people.value=[];title.value='';summary.value='';source.value='';reviewNote.value='';objective.value='';assignee.value='';transitionNote.value='';result.value='NO_FINDING';dueDate.value='';reassigning.value=false;reassignee.value='';reassignReason.value='';caseChoices.value=[];casePage.value=1;caseTotal.value=0;caseSearch.value='';caseQuery.value='';caseId.value='';linkBasis.value='';caseLinks.value=[];linkPage.value=1;linkTotal.value=0;revokeId.value='';revokeReason.value='';myPage.value=1;myTasks.value=[];myTotal.value=0;mineError.value='';mineLoading.value=false;reviewPage.value=1;reviewTasks.value=[];reviewTotal.value=0;reviewLoading.value=false;reviewError.value='' }
  return {referenceNo,priority,suggestedDueDate,myPage,reviewPage,clues,total,page,searchInput,statusInput,appliedSearch,appliedStatus,searchClues,resetClueSearch,selected,eventPage,people,caseChoices,casePage,caseTotal,caseSearch,caseId,linkBasis,caseLinks,linkPage,linkTotal,revokeId,revokeReason,reassigning,reassignee,reassignReason,reassignTask,searchLinkCases,nextLinkCases,nextLinks,createCaseLink,revokeCaseLink,title,summary,source,reviewNote,objective,assignee,dueDate,transitionNote,result,actorId,myTasks,myTotal,mineLoading,mineError,loadMine,reviewTasks,reviewTotal,reviewLoading,reviewError,loadReviewQueue,activate,show,nextPage,nextEvents,create,review,createTask,transition,reset}
}
