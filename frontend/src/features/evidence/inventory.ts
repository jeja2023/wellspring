import { ref, type Ref } from 'vue'
import { request } from '../../shared/api/client'

type Evidence = { id:string; version:number; balance:string }
type Observation = { id:string; book_weight:string; observed_weight:string; difference:string; note:string; actor_id:string; evidence_version:number; created_at:string }
type Page<T> = { items:T[]; total:number; has_more:boolean }
type Deps = { token:Ref<string>; selected:Ref<string>; selectedItem:Readonly<Ref<Evidence | undefined>>; notice:Ref<string>; error:Ref<string>; run:(f:()=>Promise<void>)=>Promise<void>; command:(name:string,path:string,data:unknown)=>Promise<unknown>; refreshEvidence:()=>Promise<void> }

export function createInventory(d:Deps) {
  const observations=ref<Observation[]>([]), total=ref(0), page=ref(1), observedWeight=ref(''), note=ref('')
  async function load(id=d.selected.value, targetPage=page.value) {
    const result:Page<Observation>=await request(`/evidence/${id}/inventory-observations?page=${targetPage}&page_size=20`,d.token.value)
    if (d.selected.value!==id) return
    observations.value=result.items;total.value=result.total;page.value=targetPage
  }
  async function move(delta:number) { await d.run(async()=>{await load(d.selected.value,page.value+delta)}) }
  async function submit() {
    const item=d.selectedItem.value
    if (!item) return
    await d.run(async()=>{
      await d.command('evidence-inventory',`/evidence/${item.id}/inventory-observations`,{evidence_version:item.version,observed_weight:observedWeight.value,note:note.value})
      observedWeight.value='';note.value='';d.notice.value='盘点已记录；账面余额未改变'
      try { await Promise.all([d.refreshEvidence(),load(item.id,1)]) }
      catch { d.error.value='盘点已成功，但页面刷新失败。请重新查看，避免重复提交。' }
    })
  }
  function reset() { observations.value=[];total.value=0;page.value=1;observedWeight.value='';note.value='' }
  return {observations,total,page,observedWeight,note,load,move,submit,reset}
}
