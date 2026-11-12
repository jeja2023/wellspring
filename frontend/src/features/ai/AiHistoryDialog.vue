<script setup lang="ts">
import {onBeforeUnmount,onMounted,ref} from 'vue'
import {useWorkspace} from '../../app/workspace'
import {createLatestRequests,isCancelled} from '../../shared/api/client'
import {formatTimestamp} from '../../shared/time'
import FormDialog from '../../shared/components/FormDialog.vue'
import Pagination from '../../shared/components/Pagination.vue'
import {modes,statuses,type AiRun} from './types'
const emit=defineEmits<{close:[]}>()
const {api}=useWorkspace(),requests=createLatestRequests(api)
const rows=ref<AiRun[]>([]),page=ref(1),total=ref(0),loading=ref(false),reading=ref(false),error=ref(''),notice=ref(''),selected=ref<AiRun|null>(null)
let alive=true,pollTimer:ReturnType<typeof setTimeout>|undefined
const running=(row:AiRun)=>['QUEUED','RUNNING'].includes(row.status)
function schedule(){clearTimeout(pollTimer);if(alive&&(rows.value.some(running)||(selected.value&&running(selected.value))))pollTimer=setTimeout(async()=>{await load();if(alive&&selected.value&&running(selected.value))await detail(selected.value.id)},1500)}
async function load(target=page.value){loading.value=true;error.value='';try{const result=await requests.latest<{items:AiRun[];page:number;total:number}>('history',`/ai/runs?page=${target}`);rows.value=result.items;page.value=result.page;total.value=result.total;schedule()}catch(failure){if(alive&&!isCancelled(failure))error.value=failure instanceof Error?failure.message:'记录加载失败'}finally{if(alive)loading.value=false}}
async function detail(id:string){reading.value=true;error.value='';notice.value='';try{selected.value=await requests.latest<AiRun>('detail',`/ai/runs/${id}`);rows.value=rows.value.map(row=>row.id===selected.value!.id?{...row,...selected.value!}:row);schedule()}catch(failure){if(alive&&!isCancelled(failure))error.value=failure instanceof Error?failure.message:'结果加载失败'}finally{if(alive)reading.value=false}}
async function copy(){try{await navigator.clipboard.writeText(selected.value?.output_text||'');if(alive)notice.value='已复制结果'}catch{if(alive)notice.value='当前浏览器无法复制，可选择结果文本或下载结果'}}
function download(){const row=selected.value;if(!row?.output_text)return;const url=URL.createObjectURL(new Blob([`智能研判结果 · 待人工核验\n模型：${row.model}\n任务：${row.id}\n\n${row.output_text}`],{type:'text/plain;charset=utf-8'}));const link=document.createElement('a');link.href=url;link.download=`研判结果-${row.id}.txt`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
onMounted(()=>{void load()});onBeforeUnmount(()=>{alive=false;clearTimeout(pollTimer);requests.dispose()})
</script>
<template>
  <FormDialog title="我的生成记录" :wide="true" :error="error" @close="emit('close')">
    <div class="page-toolbar page-toolbar-actions"><button type="button" class="secondary" :disabled="loading" @click="load()">{{loading?'正在加载…':'刷新记录'}}</button></div>
    <div class="table-wrap"><table class="ai-history-table" aria-label="个人生成记录"><thead><tr><th scope="col" class="row-number">序号</th><th scope="col">处理方式</th><th scope="col">模型</th><th scope="col">状态</th><th scope="col">创建时间</th><th scope="col">操作</th></tr></thead>
      <tbody><tr v-for="(row,index) in rows" :key="row.id"><td class="row-number">{{(page-1)*20+index+1}}</td><td>{{modes[row.mode as keyof typeof modes]||'其他任务'}}</td><td>{{row.model}}</td><td>{{statuses[row.status]}}</td><td>{{formatTimestamp(row.created_at)}}</td><td><button type="button" class="link" :disabled="reading" @click="detail(row.id)">查看结果</button></td></tr></tbody></table><p v-if="!rows.length&&!loading" class="empty">暂无个人生成记录</p></div>
    <Pagination :page="page" :total="total" :loading="loading" @change="load($event)"/>
    <p v-if="reading" class="muted" role="status">正在读取结果…</p>
    <section v-if="selected" class="ai-history-result"><div class="page-toolbar"><h3>研判结果</h3><span class="tag">{{statuses[selected.status]}}</span></div><p class="muted ai-hint">{{modes[selected.mode as keyof typeof modes]||'其他任务'}} · {{selected.model}} · {{formatTimestamp(selected.created_at)}} · 待人工核验</p>
      <p v-if="selected.error_message" :class="selected.status==='FAILED'?'error':'warning'" role="status">{{selected.error_message}}</p><p v-if="['QUEUED','RUNNING'].includes(selected.status)" class="muted" role="status">任务正在生成，可稍后刷新结果。</p><p v-if="selected.truncated" class="warning">输出达到长度上限，内容可能不完整。</p>
      <pre v-if="selected.output_text" class="ai-result">{{selected.output_text}}</pre><p v-if="notice" class="success" role="status">{{notice}}</p><div class="ai-inline-actions"><button type="button" class="secondary" :disabled="reading" @click="detail(selected.id)">刷新结果</button><button v-if="selected.output_text" type="button" class="secondary" @click="copy">复制结果</button><button v-if="selected.output_text" type="button" class="secondary" @click="download">下载结果</button></div>
    </section>
  </FormDialog>
</template>
