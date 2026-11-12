import {computed,ref} from 'vue'
import {ApiError,createLatestRequests,isCancelled,type ApiRequest} from '../../shared/api/client'
import {newIdempotencyKey} from '../../shared/api/idempotency'
import type {AiRun,AiStatus} from '../ai/types'

export function createInterpretation(api:ApiRequest,captureSession:()=>()=>boolean){
  const requests=createLatestRequests(api),service=ref<AiStatus|null>(null),active=ref<AiRun|null>(null)
  const days=ref<7|30|90>(30),consent=ref(false),busy=ref(false),checking=ref(false),refreshing=ref(false),error=ref('')
  const pending=ref<{key:string;body:string}|null>(null)
  const running=computed(()=>!!active.value&&['QUEUED','RUNNING'].includes(active.value.status))
  const canGenerate=computed(()=>!!service.value?.available&&consent.value&&!busy.value&&!running.value)
  let visible=false,disposed=false,timer:ReturnType<typeof setTimeout>|undefined,runVersion=0
  function stop(){clearTimeout(timer);timer=undefined}
  function schedule(){stop();if(visible&&!disposed&&running.value)timer=setTimeout(()=>{void refresh()},1500)}
  async function check(){checking.value=true;try{const value=await requests.latest<AiStatus>('service','/ai/status');if(!disposed)service.value=value}catch(failure){if(!disposed&&!isCancelled(failure))error.value=failure instanceof Error?failure.message:'无法读取模型服务状态'}finally{if(!disposed)checking.value=false}}
  async function refresh(){
    const id=active.value?.id;if(!id||disposed)return
    const version=++runVersion;stop();refreshing.value=true
    try{const value=await requests.latest<AiRun>('run',`/ai/runs/${id}`);if(disposed||version!==runVersion||active.value?.id!==id)return;active.value=value;error.value='';schedule()}
    catch(failure){if(!disposed&&version===runVersion&&!isCancelled(failure))error.value=(failure instanceof Error?failure.message:'任务读取失败')+'；可点击刷新结果继续查看。'}
    finally{if(!disposed&&version===runVersion)refreshing.value=false}
  }
  function enter(period:7|30|90){
    visible=true;consent.value=false
    if(!pending.value&&!running.value){if(days.value!==period)active.value=null;days.value=period}
    void check();if(active.value)void refresh()
  }
  function leave(){visible=false;stop();consent.value=false}
  async function generate(){
    if(!canGenerate.value)return
    busy.value=true;error.value='';const valid=captureSession()
    pending.value??={key:newIdempotencyKey(),body:JSON.stringify({mode:'dashboard',days:days.value,text:'',question:'',consent:true})}
    try{
      const result=await api<AiRun>('/ai/runs',{method:'POST',headers:{'Idempotency-Key':pending.value.key},body:pending.value.body})
      if(disposed||!valid())return
      pending.value=null;active.value=result;consent.value=false;await refresh()
    }catch(failure){if(disposed||!valid()||isCancelled(failure))return;if(failure instanceof ApiError&&failure.definitive)pending.value=null;error.value=failure instanceof Error?failure.message:'提交失败，请重试'}
    finally{if(!disposed&&valid())busy.value=false}
  }
  async function cancel(){
    const id=active.value?.id;if(!id||busy.value)return
    busy.value=true;error.value='';stop();runVersion++;requests.cancel();refreshing.value=false
    const valid=captureSession()
    try{const result=await api<AiRun>(`/ai/runs/${id}/cancel`,{method:'POST'});if(!disposed&&valid()&&active.value?.id===id)active.value=result}
    catch(failure){if(!disposed&&valid()&&!isCancelled(failure))error.value=failure instanceof Error?failure.message:'取消失败，请刷新结果核对'}
    finally{if(!disposed&&valid())busy.value=false}
  }
  function dispose(){disposed=true;leave();requests.dispose()}
  return {service,active,days,consent,busy,checking,refreshing,error,pending,running,canGenerate,enter,leave,check,refresh,generate,cancel,dispose}
}
