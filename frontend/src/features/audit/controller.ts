import {reactive,ref} from 'vue'
import {createLatestRequests,isCancelled,type ApiRequest} from '../../shared/api/client'

export type AuditRecord={id:string;action:string;action_name:string;object_id:string;created_at:string;username?:string;organization?:string}
type AuditPage={items:AuditRecord[];total:number;has_more:boolean}
type Filters={username:string;action:string;object_id:string;start_date:string;end_date:string}
const empty=():Filters=>({username:'',action:'',object_id:'',start_date:'',end_date:''})
export const AUDIT_PAGE_SIZE=15

/** Commit filters, page and results together, keeping the last successful page on failure. */
export function createAuditHistory(api:ApiRequest,scope:'mine'|'system'){
  const queries=createLatestRequests(api),filters=reactive(empty()),applied=ref(empty())
  const items=ref<AuditRecord[]>([]),page=ref(1),total=ref(0),more=ref(false),loading=ref(false),error=ref('')
  let generation=0,active=true
  async function load(next=page.value,selection=applied.value){
    const current=++generation,query={...selection}
    loading.value=true;error.value=''
    try{
      let response:AuditPage
      if(scope==='mine'){
        const parameters=new URLSearchParams({page:String(next),page_size:String(AUDIT_PAGE_SIZE)})
        for(const key of ['action','object_id','start_date','end_date'] as const)if(query[key])parameters.set(key,query[key])
        response=await queries.latest<AuditPage>('history','/audit/mine?'+parameters)
      }else response=await queries.latest<AuditPage>('history','/admin/audit/search',{method:'POST',body:JSON.stringify({username:query.username,action:query.action,page:next,page_size:AUDIT_PAGE_SIZE})})
      if(!active||current!==generation)return false
      items.value=response.items;total.value=response.total;more.value=response.has_more;page.value=next;applied.value=query
      return true
    }catch(failure){if(active&&current===generation&&!isCancelled(failure))error.value=failure instanceof Error?failure.message:'查询失败，请重试';return false}
    finally{if(active&&current===generation)loading.value=false}
  }
  function search(){return load(1,Object.fromEntries(Object.entries(filters).map(([key,value])=>[key,value.trim()])) as Filters)}
  function reset(){Object.assign(filters,empty());return load(1,empty())}
  function dispose(){active=false;generation++;queries.dispose()}
  return {filters,applied,items,page,total,more,loading,error,load,search,reset,dispose}
}
