import { computed, ref, type Ref } from 'vue'
import { request } from '../../shared/api/client'

type Page<T> = { items: T[]; total: number; has_more: boolean }
export type Clue = { id: string; title: string; summary: string; source: string; status: string; version: number }
type Task = { id: string; objective: string; assignee_id: string; due_date: string | null; status: string; result: string | null; version: number }
type Event = { id: string; action: string; note: string; result: string | null; actor_id: string; created_at: string }
type Person = { id: string; username: string }
type Detail = { clue: Clue; task: Task | null; events: Page<Event> }
type Dependencies = { token: Ref<string>; username: Ref<string>; notice: Ref<string>; error: Ref<string>; run: (fn: () => Promise<void>) => Promise<void>; command: (name: string, path: string, data: unknown) => Promise<unknown> }

export function createIntelligence(d: Dependencies) {
  const clues=ref<Clue[]>([]), total=ref(0), page=ref(1), selected=ref<Detail|null>(null), eventPage=ref(1)
  const people=ref<Person[]>([])
  const title=ref(''), summary=ref(''), source=ref(''), reviewNote=ref(''), objective=ref(''), assignee=ref('')
  const transitionNote=ref(''), result=ref('NO_FINDING'), dueDate=ref('')
  const myTasks=ref<(Task & {clue_title:string})[]>([]), myTotal=ref(0), mineLoading=ref(false), mineError=ref('')
  const actorId=computed(()=>people.value.find(x=>x.username===d.username.value)?.id)
  async function api(path:string) { return request(path,d.token.value) }
  async function loadList() { const r:Page<Clue>=await api(`/intelligence/clues?page=${page.value}&page_size=20`); clues.value=r.items;total.value=r.total }
  async function loadPeople() { people.value=await api('/intelligence/assignees') }
  async function loadDetail(id:string) { selected.value=await api(`/intelligence/clues/${id}/detail?page=${eventPage.value}&page_size=20`) }
  async function loadMine() {
    mineLoading.value=true;mineError.value=''
    try { const response:Page<Task & {clue_title:string}>=await api('/intelligence/tasks/mine?page=1&page_size=5');myTasks.value=response.items;myTotal.value=response.total }
    catch { myTasks.value=[];myTotal.value=0;mineError.value='待办加载失败，请重试。' }
    finally { mineLoading.value=false }
  }
  async function activate() { await d.run(async()=>{await Promise.all([loadList(),loadPeople()])}) }
  async function show(id:string) { await d.run(async()=>{eventPage.value=1;await loadDetail(id)}) }
  async function nextPage(delta:number) { await d.run(async()=>{const previous=page.value;page.value+=delta;try {await loadList()} catch(e){page.value=previous;throw e}}) }
  async function nextEvents(delta:number) { if(!selected.value)return;await d.run(async()=>{const previous=eventPage.value;eventPage.value+=delta;try {await loadDetail(selected.value!.clue.id)} catch(e){eventPage.value=previous;throw e}}) }
  async function refreshAfterWrite(message:string, id?:string) {
    d.notice.value=message
    try { await loadList(); if(id) await loadDetail(id) }
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
  function reset() { clues.value=[]; total.value=0;page.value=1;selected.value=null;eventPage.value=1;people.value=[];title.value='';summary.value='';source.value='';reviewNote.value='';objective.value='';assignee.value='';transitionNote.value='';result.value='NO_FINDING';dueDate.value='';myTasks.value=[];myTotal.value=0;mineError.value='';mineLoading.value=false }
  return {clues,total,page,selected,eventPage,people,title,summary,source,reviewNote,objective,assignee,dueDate,transitionNote,result,actorId,myTasks,myTotal,mineLoading,mineError,loadMine,activate,show,nextPage,nextEvents,create,review,createTask,transition,reset}
}
