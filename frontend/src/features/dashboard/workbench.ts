import {ref} from 'vue'
import {createLatestRequests,isCancelled,type ApiRequest} from '../../shared/api/client'

export type WorkQueue='todo'|'review'|'overdue'|'due_today'
export type WorkModule='intelligence'|'persons'|'places'|'wastewater'
export type WorkItem={module:WorkModule;kind:string;queue:'todo'|'review';id:string;resource_id:string;title:string;status:string;due_date:string|null;created_at:string;tab:string;keyword:string|null;scope:'mine'|'unit'|'claim';overdue_days:number;due_today:boolean}
export type WorkFocus=Pick<WorkItem,'module'|'kind'|'id'|'resource_id'|'tab'|'keyword'>
export type Workbench={items:WorkItem[];total:number;page:number;page_size:number;has_more:boolean;counts:Record<WorkQueue,number>;queue:WorkQueue;module:string;available_modules:{key:WorkModule;name:string}[];generated_at:string;today:string}
export const queueNames:Record<WorkQueue,string>={todo:'待办理',review:'待复核',overdue:'已逾期',due_today:'今日到期'}
export const moduleNames:Record<WorkModule,string>={intelligence:'情报线索',persons:'人员档案',places:'重点场所',wastewater:'污水监测'}
export const kindNames:Record<string,string>={investigation:'核查工单',delivery:'线索流转','person-task':'人员待办','person-identity':'身份核验','person-record':'人员业务核验','person-transfer':'责任交接',inspection:'巡查整改',incident:'场所事件','water-result':'检测结果'}
export function stateName(item:WorkItem){
  const labels:Record<string,Record<string,string>>={
    investigation:{OPEN:'待办理',RETURNED:'退回补充',PENDING_REVIEW:'待复核'},
    delivery:{OPEN:'待接收',PROCESSING:'处置中',RETURNED:'退回补充',PENDING_REVIEW:'待复核'},
    'person-task':{OPEN:'待办理'},'person-identity':{UNVERIFIED:'待核验'},'person-record':{PENDING:'待核验',RETURNED:'退回补充'},
    'person-transfer':{PENDING:'待接收'},inspection:{OPEN:'待整改复查'},incident:{DRAFT:'待核验',RETURNED:'退回补充',OPEN:'待处置',SUBMITTED:'待复核办结'},
    'water-result':{DRAFT:'待复核',RETURNED:'退回修订'},
  }
  return labels[item.kind]?.[item.status]||'待核对'
}
export function createWorkbench(api:ApiRequest){
  const requests=createLatestRequests(api),data=ref<Workbench|null>(null),loading=ref(false),error=ref('')
  let alive=true,sequence=0
  async function load(page=data.value?.page||1,queue:WorkQueue=data.value?.queue||'todo',module=data.value?.module||'all'){
    const current=++sequence;loading.value=true;error.value=''
    try{
      const query=new URLSearchParams({page:String(page),page_size:'10',queue,module})
      const result=await requests.latest<Workbench>('tasks',`/workbench/tasks?${query}`)
      if(alive&&current===sequence)data.value=result
    }catch(failure){if(alive&&current===sequence&&!isCancelled(failure))error.value=failure instanceof Error?failure.message:'事项加载失败，请重试。'}
    finally{if(alive&&current===sequence)loading.value=false}
  }
  function dispose(){alive=false;sequence++;requests.dispose();data.value=null}
  return {data,loading,error,load,dispose}
}
