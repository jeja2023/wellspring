<script setup lang="ts">
import Pagination from '../../shared/components/Pagination.vue'
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useWorkspace } from '../../app/workspace'
import { createLatestRequests, isCancelled, RequestCancelled } from '../../shared/api/client'
import { loadCaseInformation } from './caseInformation'
import type { CaseInformation } from './spreadsheet'

const props=defineProps<{intakeId:string}>()
const emit=defineEmits<{close:[];saved:[]}>()
const {api,command,captureSession,openCase}=useWorkspace()
const requests=createLatestRequests(api),dialog=ref<HTMLDialogElement|null>(null)
let mounted=true
onBeforeUnmount(()=>{mounted=false;requests.dispose()})
const source=ref<CaseInformation|null>(null),error=ref(''),notice=ref(''),busy=ref(false)
const form=reactive({mode:'NEW',number:'',title:'',case_id:'',basis:''})
type CaseChoice={id:string;number:string;title:string}
const choices=ref<CaseChoice[]>([]),query=ref(''),appliedQuery=ref(''),choicePage=ref(1),choiceTotal=ref(0)
function ensure(valid:()=>boolean){if(!mounted||!valid())throw new RequestCancelled()}
async function act(fn:(check:()=>void)=>Promise<void>){const valid=captureSession();busy.value=true;error.value='';try{await fn(()=>ensure(valid))}catch(e){if(!isCancelled(e)&&mounted&&valid())error.value=e instanceof Error?e.message:'操作未完成'}finally{busy.value=false}}
async function load(){await act(async check=>{const row=await loadCaseInformation(api,props.intakeId);check();source.value=row;form.title=`接警${row['接警编号']}相关案件`})}
async function loadChoices(target=1,keyword=appliedQuery.value){await act(async check=>{const response=await requests.latest<{items:CaseChoice[];total:number}>('choices',`/cases?page=${target}&page_size=20&q=${encodeURIComponent(keyword)}`);check();choices.value=response.items;choiceTotal.value=response.total;choicePage.value=target;appliedQuery.value=keyword;form.case_id=''})}
async function transfer(){if(!source.value)return;await act(async check=>{
  const payload={source_version:source.value!.version,mode:form.mode,basis:form.basis,...(form.mode==='NEW'?{number:form.number,title:form.title}:{case_id:form.case_id})}
  const result=await command(`intake-case-link-${props.intakeId}`,`/case-information/${props.intakeId}/case-link`,payload) as CaseChoice
  check();source.value={...source.value!,case_link:{linked:true,accessible:true,...result},version:source.value!.version!+1};notice.value=form.mode==='NEW'?'案件记录已创建，原接警信息和来源快照已保留。':'已关联已有案件，未重复创建案件。';emit('saved')
})}
async function navigate(){const number=source.value?.case_link?.number;if(!number)return;emit('close');await openCase(number)}
onMounted(()=>{dialog.value?.showModal();void load()})
</script>

<template>
  <dialog ref="dialog" class="case-information-dialog" aria-labelledby="intake-transfer-title" @close="emit('close')" @cancel="busy&&$event.preventDefault()">
    <div class="case-detail-heading"><h2 id="intake-transfer-title">接警转办与案件关联</h2><button type="button" class="link" :disabled="busy" @click="dialog?.close()" aria-label="关闭转办窗口">关闭</button></div>
    <p>原接警信息保留，案件编号和名称由你核对填写；创建的是案件记录，不代表正式立案或并案。</p>
    <p v-if="busy" role="status">正在处理…</p><p v-if="error" class="error" role="alert">{{error}} <button type="button" class="link" :disabled="busy" @click="load">重新核对</button></p><p v-if="notice" class="success" role="status">{{notice}}</p>
    <template v-if="source"><p><b>来源接警编号：{{source['接警编号']}}</b> · 当前版本 {{source.version}}</p><p class="muted intake-preview">{{source['报警内容']||'未填写报警内容'}}</p>
      <template v-if="source.case_link"><p>此接警信息已关联案件：{{source.case_link.accessible?`${source.case_link.number} · ${source.case_link.title}`:'已有关联，当前账号没有该案件访问权限'}}。</p><button v-if="source.case_link.accessible" type="button" :disabled="busy" @click="navigate">查看案件</button></template>
      <p v-else-if="!source.can_link_case" class="muted">当前账号仅能查看此接警信息，转办需由所属组织账号办理。</p>
      <template v-else><label>办理方式<select v-model="form.mode" :disabled="busy" @change="form.mode==='EXISTING'&&loadChoices()"><option value="NEW">创建新的案件记录</option><option value="EXISTING">关联已有案件</option></select></label>
        <form v-if="form.mode==='EXISTING'" class="actions" @submit.prevent="loadChoices(1,query.trim())"><label>查找已有案件<input v-model="query" maxlength="100" placeholder="案件编号或名称"></label><button type="submit" class="secondary" :disabled="busy">查找案件</button></form>
        <Pagination v-if="form.mode==='EXISTING'" :page="choicePage" :total="choiceTotal" :loading="busy" @change="loadChoices($event)" />
        <form @submit.prevent="transfer"><template v-if="form.mode==='NEW'"><label>案件编号<input v-model="form.number" maxlength="80" required :disabled="busy"></label><label>案件名称<input v-model="form.title" maxlength="200" required :disabled="busy"></label></template><label v-else>已有案件<select v-model="form.case_id" required :disabled="busy"><option value="" disabled>选择本组织案件</option><option v-for="row in choices" :key="row.id" :value="row.id">{{row.number}} · {{row.title}}</option></select></label><label>转办 / 关联依据<textarea v-model="form.basis" maxlength="1000" required :disabled="busy"></textarea></label><button :disabled="busy">{{form.mode==='NEW'?'确认创建并关联':'确认关联已有案件'}}</button></form>
      </template>
    </template>
  </dialog>
</template>
