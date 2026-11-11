<script setup lang="ts">
import {onBeforeUnmount,reactive,ref} from 'vue'
import FormDialog from '../../shared/components/FormDialog.vue'
import {useWorkspace} from '../../app/workspace'
import {isCancelled} from '../../shared/api/client'
import {today,type Incident} from './types'
const props=defineProps<{placeId:string;kind:'inspection'|'incident';incident?:Incident}>(),emit=defineEmits<{close:[];saved:[]}>()
const {command,captureSession}=useWorkspace(),busy=ref(false),error=ref('')
function localTime(value?:string){const date=value?new Date(value):new Date();return new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16)}
const form=reactive({inspected_on:today(),findings:'',requires_action:false,due_on:'',title:props.incident?.title||'',occurred_at:localTime(props.incident?.occurred_at),source:props.incident?.source||'',facts:props.incident?.facts||'',material_ref:props.incident?.material_ref||''})
let alive=true;onBeforeUnmount(()=>{alive=false})
async function save(){busy.value=true;error.value='';const valid=captureSession();try{
 const body=props.kind==='inspection'?{inspected_on:form.inspected_on,findings:form.findings,requires_action:form.requires_action,due_on:form.requires_action?form.due_on:null}:{title:form.title,occurred_at:new Date(form.occurred_at).toISOString(),source:form.source,facts:form.facts,material_ref:form.material_ref,...(props.incident?{version:props.incident.version}:{})}
 const path=props.incident?`/places/incidents/${props.incident.id}/update`:`/places/${props.placeId}/${props.kind==='inspection'?'inspections':'incidents'}`
 await command('place-record-'+path,path,body);if(alive&&valid())emit('saved')
 }catch(e){if(alive&&!isCancelled(e))error.value=e instanceof Error?e.message:'保存失败'}finally{if(alive)busy.value=false}}
</script>
<template><FormDialog :title="kind==='inspection'?'登记场所巡查':incident?'补充事件资料':'登记场所事件'" :wide="true" :busy="busy" :error="error" @close="emit('close')"><form @submit.prevent="save"><template v-if="kind==='inspection'"><label>巡查日期<input v-model="form.inspected_on" type="date" :max="today()" required></label><label>现场情况 / 发现问题<textarea v-model="form.findings" maxlength="5000" required></textarea></label><label class="check-label"><input v-model="form.requires_action" type="checkbox">需要整改复查</label><label v-if="form.requires_action">整改期限<input v-model="form.due_on" type="date" :min="form.inspected_on" required></label></template><template v-else><label>事件标题<input v-model="form.title" maxlength="200" required></label><div class="place-fields"><label>发生时间<input v-model="form.occurred_at" type="datetime-local" :max="localTime()" required></label><label>信息来源<input v-model="form.source" maxlength="200" required></label></div><label>具体事实<textarea v-model="form.facts" maxlength="5000" required></textarea></label><label>资料引用 / 文书或报告编号<input v-model="form.material_ref" maxlength="500" required></label><p class="muted">只记录具体事件与来源，保存后由另一名有权限人员核验。</p></template><button :disabled="busy">{{kind==='inspection'?'保存巡查':'保存待核验事件'}}</button></form></FormDialog></template>
