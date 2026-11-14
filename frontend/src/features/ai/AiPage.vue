<script setup lang="ts">
import {computed,onBeforeUnmount,onMounted,ref} from 'vue'
import {useWorkspace} from '../../app/workspace'
import {ApiError,createLatestRequests,isCancelled} from '../../shared/api/client'
import {newIdempotencyKey} from '../../shared/api/idempotency'
import {formatTimestamp} from '../../shared/time'
import AiSettingsDialog from './AiSettingsDialog.vue'
import AiHistoryDialog from './AiHistoryDialog.vue'
import StatusBadge from '../../shared/components/StatusBadge.vue'
import {modes,statuses,type AiStatus,type AiRun} from './types'
import './ai.css'
const {api,can,isAdmin,captureSession}=useWorkspace(),requests=createLatestRequests(api)
const settingsOpen=ref(false),historyOpen=ref(false)
const service=ref<AiStatus|null>(null),mode=ref<keyof typeof modes>('summary'),text=ref(''),question=ref(''),days=ref(30),consent=ref(false)
const active=ref<AiRun|null>(null),busy=ref(false),checking=ref(false),error=ref(''),notice=ref(''),preview=ref('')
let disposed=false,pollTimer:ReturnType<typeof setTimeout>|undefined,pending:{key:string;body:string}|null=null
const running=computed(()=>active.value&&['QUEUED','RUNNING'].includes(active.value.status))
const canSubmit=computed(()=>can('ai.generate')&&service.value?.available&&!busy.value&&!running.value&&consent.value&&(mode.value==='dashboard'||!!text.value.trim())&&(mode.value!=='qa'||!!question.value.trim()))
async function check(){checking.value=true;error.value='';try{service.value=await requests.latest<AiStatus>('service','/ai/status')}catch(e){if(!isCancelled(e))error.value=e instanceof Error?e.message:'状态检查失败'}finally{checking.value=false}}
async function openRun(id:string){clearTimeout(pollTimer);error.value='';try{active.value=await requests.latest<AiRun>('run',`/ai/runs/${id}`);if(running.value)schedule(id)}catch(e){if(!isCancelled(e))error.value=e instanceof Error?e.message:'任务读取失败'}}
function schedule(id:string){clearTimeout(pollTimer);pollTimer=setTimeout(async()=>{
  if(disposed)return
  try{const result=await requests.latest<AiRun>('run',`/ai/runs/${id}`);if(active.value?.id!==id)return;active.value=result;if(running.value)schedule(id)}catch(e){if(!isCancelled(e))error.value=(e instanceof Error?e.message:'任务状态检查失败')+'；可通过“刷新结果”继续查看。'}
},1500)}
async function generate(){if(!canSubmit.value)return;busy.value=true;error.value='';notice.value='';const current=captureSession()
  const body=JSON.stringify({mode:mode.value,text:mode.value==='dashboard'?'':text.value,question:question.value,days:days.value,consent:consent.value})
  if(pending&&pending.body!==body){error.value='上次提交结果未确认，请恢复原输入重试，或先刷新个人记录核对结果。';busy.value=false;return}
  pending??={key:newIdempotencyKey(),body}
  try{const result=await api<AiRun>('/ai/runs',{method:'POST',headers:{'Idempotency-Key':pending.key},body});if(!current()||disposed)return;pending=null;active.value=result;consent.value=false;await openRun(result.id)}catch(e){if(isCancelled(e))return;if(e instanceof ApiError&&e.definitive)pending=null;error.value=e instanceof Error?e.message:'提交失败，请重试'}finally{busy.value=false}}
async function cancel(){if(!active.value)return;const id=active.value.id;busy.value=true;error.value='';try{const result=await api<AiRun>(`/ai/runs/${id}/cancel`,{method:'POST'});clearTimeout(pollTimer);if(active.value?.id===id)active.value=result}catch(e){if(!isCancelled(e))error.value=e instanceof Error?e.message:'取消失败'}finally{busy.value=false}}
async function previewStats(){error.value='';try{const result=await requests.latest('preview',`/dashboard/overview?days=${days.value}`);preview.value=JSON.stringify(result,null,2)}catch(e){if(!isCancelled(e))error.value=e instanceof Error?e.message:'统计预览失败'}}
function exportDraft(){if(!active.value?.output_text)return;const blob=new Blob([`智能研判结果 · 待人工核验\n模型：${active.value.model}\n任务：${active.value.id}\n\n${active.value.output_text}`],{type:'text/plain;charset=utf-8'});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=`研判结果-${active.value.id}.txt`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
async function copyDraft(){try{await navigator.clipboard.writeText(active.value?.output_text||'');notice.value='已复制结果'}catch{notice.value='当前浏览器无法复制，请选择结果文本或下载结果'}}
function settingsSaved(){settingsOpen.value=false;consent.value=false;notice.value='模型服务配置已保存';void check()}
onMounted(()=>{void check()})
onBeforeUnmount(()=>{disposed=true;requests.dispose();clearTimeout(pollTimer)})
</script>
<template>
  <div class="page-list ai-page">
    <p v-if="error" class="error" role="alert">{{error}}</p><p v-if="notice" class="success" role="status">{{notice}}</p>
    <section class="card"><div class="page-toolbar"><div class="ai-service-status"><StatusBadge :tone="service?.available?'success':'warning'">{{service?.available?'服务已启用':'服务未就绪'}}</StatusBadge><span>{{service?.model||'尚未选择模型'}}</span></div><div class="ai-inline-actions"><button type="button" class="secondary" @click="historyOpen=true">我的生成记录</button><button class="secondary" :disabled="checking" @click="check">{{checking?'检查中…':'刷新服务状态'}}</button><button v-if="isAdmin" class="secondary" @click="settingsOpen=true">配置模型服务</button></div></div><p class="muted">{{service?.message||'正在读取服务状态…'}}</p><p v-if="service?.checked_at" class="muted ai-hint">最近连接检查：{{formatTimestamp(service.checked_at)}} · {{service.check_message}}</p></section>
    <section class="card"><form @submit.prevent="generate"><fieldset :disabled="busy||!!running" class="ai-form-fields"><div class="system-search ai-form-options"><label>处理方式<select v-model="mode" @change="consent=false;preview='' "><option v-for="(label,key) in modes" :key="key" :value="key" :disabled="key==='dashboard'&&!can('dashboard.read')">{{label}}</option></select></label><label v-if="mode==='dashboard'">统计周期<select v-model.number="days" @change="preview='';consent=false"><option :value="7">近 7 天</option><option :value="30">近 30 天</option><option :value="90">近 90 天</option></select></label></div>
      <template v-if="mode!=='dashboard'"><label>待处理文本<textarea v-model="text" :maxlength="service?.max_input_chars||20000" rows="9" required placeholder="粘贴需要摘要、提取或问答的资料。请先检查内容和服务接收范围。"></textarea></label><p class="muted ai-hint">{{text.length.toLocaleString()}} / {{service?.max_input_chars||20000}} 字符；原文不会保存到任务历史。</p></template>
      <template v-else><p class="muted">只提交当前组织、当前角色可查询模块的汇总统计，不提交业务原文和个人明细。</p><button type="button" class="secondary" @click="previewStats">预览汇总数据</button><details v-if="preview" class="ai-preview"><summary>查看统计预览</summary><pre>{{preview}}</pre></details></template>
      <label>{{mode==='qa'?'问题':'补充要求（可选）'}}<textarea v-model="question" maxlength="2000" rows="2" :required="mode==='qa'" placeholder="例如：按事实、依据、待核实事项分项输出"></textarea></label>
      <label class="check-label ai-consent"><input v-model="consent" type="checkbox" required>我已核对内容，确认发送至管理员配置的模型服务。</label><p class="muted ai-hint">结果由 AI 辅助生成，待人工核验，不会自动写入案件或其他业务记录。</p></fieldset><div class="actions"><button type="submit" :disabled="!canSubmit">{{busy?'提交中…':running?'正在生成…':'生成研判结果'}}</button><span v-if="!can('ai.generate')" class="muted">当前角色没有模型生成权限</span></div></form></section>
    <section v-if="active" class="card"><div class="page-toolbar"><h2>研判结果</h2><StatusBadge :tone="active.status==='FAILED'?'danger':active.status==='SUCCEEDED'?'success':'info'">{{statuses[active.status]}} · 待人工核验</StatusBadge></div><p class="muted ai-hint">模型 {{active.model}} · {{formatTimestamp(active.created_at)}} · 输入 {{active.input_chars}} 字符<span v-if="active.duration_ms!==null"> · 耗时 {{(active.duration_ms/1000).toFixed(1)}} 秒</span></p><p v-if="active.error_message" :class="active.status==='FAILED'?'error':'warning'" role="status">{{active.error_message}}</p><p v-if="running" class="muted" role="status">模型正在处理，可离开页面，稍后从个人记录查看。取消后不会保存迟到的结果。</p><p v-if="active.truncated" class="warning">输出达到长度上限，内容可能不完整。可缩小输入或调整模型输出长度。</p><div v-if="active.output_text" class="ai-guardrail-banner">以下内容由 AI 辅助生成，仅供办案参考，请人工核对原文与依据后再使用。</div><pre v-if="active.output_text" class="ai-result">{{active.output_text}}</pre><div class="actions"><button type="button" class="secondary" :disabled="busy" @click="openRun(active.id)">刷新结果</button><button v-if="running" type="button" class="secondary" :disabled="busy" @click="cancel">取消任务</button><button v-if="active.output_text" class="secondary" @click="copyDraft">复制结果</button><button v-if="active.output_text" class="secondary" @click="exportDraft">下载结果</button></div></section>
    <AiHistoryDialog v-if="historyOpen" @close="historyOpen=false"/>
    <AiSettingsDialog v-if="settingsOpen&&isAdmin" @close="settingsOpen=false" @saved="settingsSaved"/>
  </div>
</template>
