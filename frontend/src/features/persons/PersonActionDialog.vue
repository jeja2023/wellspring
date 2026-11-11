<script setup lang="ts">
import {computed,reactive,ref} from 'vue'
import {useWorkspace} from '../../app/workspace'
import {isCancelled} from '../../shared/api/client'
import FormDialog from '../../shared/components/FormDialog.vue'
import {today,type Profile,type PersonRecord} from './types'
const props=defineProps<{person:Profile;record?:PersonRecord|null;mode:'review'|'execute'}>(),emit=defineEmits<{close:[];saved:[]}>()
const {command,captureSession}=useWorkspace(),busy=ref(false),error=ref('')
const options=computed(()=>props.mode==='review'?((props.record?.verification_status||props.person.verification_status)==='VERIFIED'?{REVOKE:'撤销核验'}:{CONFIRM:'核验确认',RETURN:'退回补充',REVOKE:'撤销记录'}):props.record?.state==='DECIDED'?{...(props.record?.record_type==='COMMUNITY'||props.record?.record_type==='REHABILITATION'?{REPORT:'实际报到'}:{ADMIT:'实际入所 / 开始治疗'}),CHANGE:'措施变更',CANCEL:'撤销措施'}:{RELEASE:'实际解除 / 结束',CHANGE:'措施变更',CANCEL:'撤销措施'})
const form=reactive({action:Object.keys(options.value)[0],note:'',document_no:'',occurred_on:today()})
async function submit(){busy.value=true;error.value='';const current=captureSession();try{const route=props.mode==='execute'?`/person-drafts/records/${props.record!.id}/execute`:props.record?`/person-drafts/records/${props.record.id}/review`:`/person-drafts/${props.person.id}/identity-review`;await command('person-action-'+(props.record?.id||props.person.id),route,{version:props.record?.version||props.person.version,action:form.action,note:form.note,document_no:form.document_no,...(props.mode==='execute'?{occurred_on:form.occurred_on}:{})});if(current())emit('saved')}catch(e){if(!isCancelled(e))error.value=e instanceof Error?e.message:'办理失败'}finally{busy.value=false}}
</script>
<template><FormDialog :title="mode==='execute'?'登记措施执行事件':record?'核验业务记录':'核验人员身份'" :busy="busy" :error="error" @close="emit('close')"><form @submit.prevent="submit"><p>{{person.name}} · {{record?'业务记录版本 '+record.version:'主档版本 '+person.version}}</p><label>办理动作<select v-model="form.action"><option v-for="(label,key) in options" :key="key" :value="key">{{label}}</option></select></label><label v-if="mode==='execute'">实际发生日期<input v-model="form.occurred_on" type="date" :max="today()" required></label><label>依据文书 / 核验编号<input v-model="form.document_no" maxlength="200" required></label><label>办理意见<textarea v-model="form.note" maxlength="2000" required></textarea></label><p class="muted person-hint">{{mode==='execute'?'按真实执行和文书登记，不因预计到期自动解除；变更不会自动创建下一项措施。':'核验仅确认当前资料及依据，录入人不能核验本人登记的资料。'}}</p><button :disabled="busy">确认记录</button></form></FormDialog></template>
