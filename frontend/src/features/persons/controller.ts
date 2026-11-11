import { ref, type Ref } from 'vue'
import { createLatestRequests, isCancelled, RequestCancelled, type ApiRequest } from '../../shared/api/client'
type Person = {id:string;name:string;source:string;verification_status:string;version:number;created_at:string}
type Page<T> = {items:T[];total:number;has_more:boolean}
type Deps = {api:ApiRequest;captureSession:()=>()=>boolean;notice:Ref<string>;error:Ref<string>;run:(f:()=>Promise<void>)=>Promise<void>;command:(name:string,path:string,data:unknown)=>Promise<unknown>}
export function createPersons(d:Deps) {
  const queries = createLatestRequests(d.api)
  const people=ref<Person[]>([]),page=ref(1),total=ref(0),name=ref(''),source=ref(''),searchInput=ref(''),appliedSearch=ref('')
  async function load(targetPage=page.value,keyword=appliedSearch.value) { const current=d.captureSession();
    const r:Page<Person>=await queries.latest('list','/person-drafts/search',{method:'POST',body:JSON.stringify({keyword,page:targetPage,page_size:20})}); if(!current())throw new RequestCancelled()
    people.value=r.items;total.value=r.total;page.value=targetPage;appliedSearch.value=keyword
  }
  async function search(){await d.run(async()=>{await load(1,searchInput.value.trim())})}
  async function clearSearch(){await d.run(async()=>{await load(1,'');searchInput.value=''})}
  async function activate(){await d.run(async()=>{await load()})}
  async function move(delta:number){await d.run(async()=>{await load(page.value+delta)})}
  async function create(){let saved=false;await d.run(async()=>{
    const current=d.captureSession()
    await d.command('person-draft','/person-drafts',{name:name.value,source:source.value})
    if (!current()) throw new RequestCancelled()
    saved=true
    name.value='';source.value='';d.notice.value='人员草稿已创建，身份尚未核验'
    try {await load(1)} catch (e) {if (isCancelled(e)) throw e; d.error.value='草稿已创建，但列表刷新失败。请重新查看，避免重复提交。'}
  });return saved}
  function reset(){queries.cancel();people.value=[];page.value=1;total.value=0;name.value='';source.value='';searchInput.value='';appliedSearch.value=''}
  return {people,page,total,name,source,searchInput,appliedSearch,search,clearSearch,activate,move,create,reset}
}
