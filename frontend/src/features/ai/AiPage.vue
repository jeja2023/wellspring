<script setup lang="ts">
import {computed,onBeforeUnmount,onMounted,ref} from 'vue'
import {useWorkspace} from '../../app/workspace'
import {ApiError,createLatestRequests,isCancelled} from '../../shared/api/client'
import {newIdempotencyKey} from '../../shared/api/idempotency'
import {formatTimestamp} from '../../shared/time'
import Pagination from '../../shared/components/Pagination.vue'
import AiSettingsDialog from './AiSettingsDialog.vue'
import {modes,statuses,type AiStatus,type AiRun} from './types'
import './ai.css'
const {api,can,isAdmin,captureSession}=useWorkspace(),requests=createLatestRequests(api)
const settingsOpen=ref(false)
const service=ref<AiStatus|null>(null),mode=ref<keyof typeof modes>('summary'),text=ref(''),question=ref(''),days=ref(30),consent=ref(false)
const active=ref<AiRun|null>(null),history=ref<AiRun[]>([]),historyPage=ref(1),total=ref(0),busy=ref(false),checking=ref(false),historyLoading=ref(false),error=ref(''),historyError=ref(''),notice=ref(''),preview=ref('')
let disposed=false,pollTimer:ReturnType<typeof setTimeout>|undefined,pending:{key:string;body:string}|null=null
const running=computed(()=>active.value&&['QUEUED','RUNNING'].includes(active.value.status))
const canSubmit=computed(()=>can('ai.generate')&&service.value?.available&&!busy.value&&!running.value&&consent.value&&(mode.value==='dashboard'||!!text.value.trim())&&(mode.value!=='qa'||!!question.value.trim()))
async function check(){checking.value=true;error.value='';try{service.value=await requests.latest<AiStatus>('service','/ai/status')}catch(e){if(!isCancelled(e))error.value=e instanceof Error?e.message:'状态检查失败'}finally{checking.value=false}}
async function loadHistory(target=historyPage.value){historyLoading.value=true;historyError.value='';try{const result=await requests.latest<{items:AiRun[];page:number;total:number}>('history',`/ai/runs?page=${target}`);history.value=result.items;historyPage.value=result.page;total.value=result.total}catch(e){if(!isCancelled(e))historyError.value=e instanceof Error?e.message:'记录加载失败'}finally{historyLoading.value=false}}
async function openRun(id:string){clearTimeout(pollTimer);error.value='';try{active.value=await requests.latest<AiRun>('run',`/ai/runs/${id}`);if(running.value)schedule(id)}catch(e){if(!isCancelled(e))error.value=e instanceof Error?e.message:'任务读取失败'}}
function schedule(id:string){clearTimeout(pollTimer);pollTimer=setTimeout(async()=>{
  if(disposed)return
  try{const result=await requests.latest<AiRun>('run',`/ai/runs/${id}`);if(active.value?.id!==id)return;active.value=result;if(running.value)schedule(id);else void loadHistory(1)}catch(e){if(!isCancelled(e))error.value=(e instanceof Error?e.message:'任务状态检查失败')+'；可通过“刷新结果”继续查看。'}
},1500)}
async function generate(){if(!canSubmit.value)return;busy.value=true;error.value='';notice.value='';const current=captureSession()
  const body=JSON.stringify({mode:mode.value,text:mode.value==='dashboard'?'':text.value,question:question.value,days:days.value,consent:consent.value})
  if(pending&&pending.body!==body){error.value='上次提交结果未确认，请恢复原输入重试，或先刷新个人记录核对结果。';busy.value=false;return}
  pending??={key:newIdempotencyKey(),body}
  try{const result=await api<AiRun>('/ai/runs',{method:'POST',headers:{'Idempotency-Key':pending.key},body});if(!current()||disposed)return;pending=null;active.value=result;consent.value=false;void loadHistory(1);await openRun(result.id)}catch(e){if(isCancelled(e))return;if(e instanceof ApiError&&e.definitive)pending=null;error.value=e instanceof Error?e.message:'提交失败，请重试'}finally{busy.value=false}}
async function cancel(){if(!active.value)return;const id=active.value.id;busy.value=true;error.value='';try{const result=await api<AiRun>(`/ai/runs/${id}/cancel`,{method:'POST'});clearTimeout(pollTimer);if(active.value?.id===id)active.value=result;void loadHistory(1)}catch(e){if(!isCancelled(e))error.value=e instanceof Error?e.message:'取消失败'}finally{busy.value=false}}
async function previewStats(){error.value='';try{const result=await requests.latest('preview',`/dashboard/overview?days=${days.value}`);preview.value=JSON.stringify(result,null,2)}catch(e){if(!isCancelled(e))error.value=e instanceof Error?e.message:'统计预览失败'}}
function exportDraft(){if(!active.value?.output_text)return;const blob=new Blob([`AI 生成草稿 · 待人工核验\n模型：${active.value.model}\n任务：${active.value.id}\n\n${active.value.output_text}`],{type:'text/plain;charset=utf-8'});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=`AI草稿-${active.value.id}.txt`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
async function copyDraft(){try{await navigator.clipboard.writeText(active.value?.output_text||'');notice.value='已复制草稿'}catch{notice.value='当前浏览器无法复制，请选择结果文本或下载草稿'}}
function settingsSaved(){settingsOpen.value=false;consent.value=false;notice.value='模型服务配置已保存';void check()}
onMounted(()=>{void check();void loadHistory(1)})
onBeforeUnmount(()=>{disposed=true;requests.dispose();clearTimeout(pollTimer)})
</script>
<template>
  <div class="page-list ai-page">
    <p v-if="error" class="error" role="alert">{{error}}</p><p v-if="notice" class="success" role="status">{{notice}}</p>
    <section class="card"><div class="page-toolbar"><div class="ai-service-status"><span class="tag">{{service?.available?'服务已启用':'服务未就绪'}}</span><span>{{service?.model||'尚未选择模型'}}</span></div><div class="ai-inline-actions"><button class="secondary" :disabled="checking" @click="check">{{checking?'检查中…':'刷新服务状态'}}</button><button v-if="isAdmin" class="secondary" @click="settingsOpen=true">配置模型服务</button></div></div><p class="muted">{{service?.message||'正在读取服务状态…'}}</p><p v-if="service?.checked_at" class="muted ai-hint">最近连接检查：{{formatTimestamp(service.checked_at)}} · {{service.check_message}}</p></section>
    <section class="card"><form @submit.prevent="generate"><fieldset :disabled="busy||!!running" class="ai-form-fields"><div class="system-search ai-form-options"><label>处理方式<select v-model="mode" @change="consent=false;preview='' "><option v-for="(label,key) in modes" :key="key" :value="key" :disabled="key==='dashboard'&&!can('dashboard.read')">{{label}}</option></select></label><label v-if="mode==='dashboard'">统计周期<select v-model.number="days" @change="preview='';consent=false"><option :value="7">近 7 天</option><option :value="30">近 30 天</option><option :value="90">近 90 天</option></select></label></div>
      <template v-if="mode!=='dashboard'"><label>待处理文本<textarea v-model="text" :maxlength="service?.max_input_chars||20000" rows="9" required placeholder="粘贴需要摘要、提取或问答的资料。请先检查内容和服务接收范围。"></textarea></label><p class="muted ai-hint">{{text.length.toLocaleString()}} / {{service?.max_input_chars||20000}} 字符；原文不会保存到任务历史。</p></template>
      <template v-else><p class="muted">只提交当前组织、当前角色可查询模块的汇总统计，不提交业务原文和个人明细。</p><button type="button" class="secondary" @click="previewStats">预览汇总数据</button><details v-if="preview" class="ai-preview"><summary>查看统计预览</summary><pre>{{preview}}</pre></details></template>
      <label>{{mode==='qa'?'问题':'补充要求（可选）'}}<textarea v-model="question" maxlength="2000" rows="2" :required="mode==='qa'" placeholder="例如：按事实、依据、待核实事项分项输出"></textarea></label>
      <label class="check-label ai-consent"><input v-model="consent" type="checkbox" required>我已核对内容，确认发送至管理员配置的模型服务。</label><p class="muted ai-hint">结果仅为 AI 草稿，需要人工核验，不会自动写入案件或其他业务记录。</p></fieldset><div class="actions"><button type="submit" :disabled="!canSubmit">{{busy?'提交中…':running?'正在生成…':'生成草稿'}}</button><span v-if="!can('ai.generate')" class="muted">当前角色没有模型生成权限</span></div></form></section>
    <section v-if="active" class="card"><div class="page-toolbar"><h2>生成结果</h2><span class="tag">{{statuses[active.status]}} · 待人工核验</span></div><p class="muted ai-hint">模型 {{active.model}} · {{formatTimestamp(active.created_at)}} · 输入 {{active.input_chars}} 字符<span v-if="active.duration_ms!==null"> · 耗时 {{(active.duration_ms/1000).toFixed(1)}} 秒</span></p><p v-if="active.error_message" :class="active.status==='FAILED'?'error':'warning'" role="status">{{active.error_message}}</p><p v-if="running" class="muted" role="status">模型正在处理，可离开页面，稍后从个人记录查看。取消后不会保存迟到的结果。</p><p v-if="active.truncated" class="warning">输出达到长度上限，内容可能不完整。可缩小输入或调整模型输出长度。</p><pre v-if="active.output_text" class="ai-result">{{active.output_text}}</pre><div class="actions"><button type="button" class="secondary" :disabled="busy" @click="openRun(active.id)">刷新结果</button><button v-if="running" type="button" class="secondary" :disabled="busy" @click="cancel">取消任务</button><button v-if="active.output_text" class="secondary" @click="copyDraft">复制草稿</button><button v-if="active.output_text" class="secondary" @click="exportDraft">下载草稿</button></div></section>
    <section class="card"><div class="page-toolbar"><h2>我的生成记录</h2><button class="secondary" :disabled="historyLoading" @click="loadHistory()">刷新记录</button></div><p v-if="historyError" class="error" role="alert">{{historyError}}</p><div class="table-wrap"><table><thead><tr><th scope="col" class="row-number">序号</th><th scope="col">处理方式</th><th scope="col">模型</th><th scope="col">状态</th><th scope="col">创建时间</th><th scope="col">操作</th></tr></thead><tbody><tr v-for="(row,index) in history" :key="row.id"><td class="row-number">{{(historyPage-1)*20+index+1}}</td><td>{{modes[row.mode as keyof typeof modes]||row.mode}}</td><td>{{row.model}}</td><td>{{statuses[row.status]}}</td><td>{{formatTimestamp(row.created_at)}}</td><td><button class="link" @click="openRun(row.id)">查看结果</button></td></tr></tbody></table><p v-if="!history.length&&!historyLoading" class="empty">暂无个人生成记录</p></div><Pagination :page="historyPage" :total="total" :loading="historyLoading" @change="loadHistory($event)"/></section>
    <AiSettingsDialog v-if="settingsOpen&&isAdmin" @close="settingsOpen=false" @saved="settingsSaved"/>
  </div>
</template>
