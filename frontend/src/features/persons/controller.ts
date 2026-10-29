import { ref, type Ref } from 'vue'
import { request } from '../../shared/api/client'
type Person = {id:string;name:string;source:string;verification_status:string;version:number;created_at:string}
type Page<T> = {items:T[];total:number;has_more:boolean}
type Deps = {token:Ref<string>;notice:Ref<string>;error:Ref<string>;run:(f:()=>Promise<void>)=>Promise<void>;command:(name:string,path:string,data:unknown)=>Promise<unknown>}
export function createPersons(d:Deps) {
  const people=ref<Person[]>([]),page=ref(1),total=ref(0),name=ref(''),source=ref(''),searchInput=ref(''),appliedSearch=ref('')
  async function load(targetPage=page.value,keyword=appliedSearch.value) {
    const r:Page<Person>=await request('/person-drafts/search',d.token.value,{method:'POST',body:JSON.stringify({keyword,page:targetPage,page_size:20})})
    people.value=r.items;total.value=r.total;page.value=targetPage;appliedSearch.value=keyword
  }
  async function search(){await d.run(async()=>{await load(1,searchInput.value.trim())})}
  async function clearSearch(){await d.run(async()=>{await load(1,'');searchInput.value=''})}
  async function activate(){await d.run(async()=>{await load()})}
  async function move(delta:number){await d.run(async()=>{await load(page.value+delta)})}
  async function create(){await d.run(async()=>{
    await d.command('person-draft','/person-drafts',{name:name.value,source:source.value})
    name.value='';source.value='';d.notice.value='人员草稿已创建，身份尚未核验'
    try {await load(1)} catch {d.error.value='草稿已创建，但列表刷新失败。请重新查看，避免重复提交。'}
  })}
  function reset(){people.value=[];page.value=1;total.value=0;name.value='';source.value='';searchInput.value='';appliedSearch.value=''}
  return {people,page,total,name,source,searchInput,appliedSearch,search,clearSearch,activate,move,create,reset}
}
