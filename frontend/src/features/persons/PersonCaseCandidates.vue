<script setup lang="ts">
import Pagination from '../../shared/components/Pagination.vue'
const {can}=useWorkspace()
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useWorkspace } from '../../app/workspace'
import { createLatestRequests, isCancelled } from '../../shared/api/client'
type Candidate={id:string;case_number:string;case_title:string;basis:string;status:string;version:number;revoke_reason:string|null}
type CaseChoice={id:string;number:string;title:string}
type Page<T>={items:T[];total:number}
const props=defineProps<{person:{id:string;name:string;version:number}}>()
const emit=defineEmits<{close:[]; updated:[version:number]}>()
const {api,loading,run,command,notice,error}=useWorkspace()
const pageRequests = createLatestRequests(api)
onBeforeUnmount(() => pageRequests.dispose())
const request = (path: string, options: RequestInit = {}) => pageRequests.latest(path.split('?')[0], path, options)
const candidates=ref<Candidate[]>([]),page=ref(1),total=ref(0),choices=ref<CaseChoice[]>([]),choicePage=ref(1),choiceTotal=ref(0)
const target=ref(''),basis=ref(''),personVersion=ref(props.person.version),revokeId=ref(''),reason=ref('')
async function load(pageNumber=page.value){const r:Page<Candidate>=await request(`/person-drafts/${props.person.id}/case-candidates?page=${pageNumber}&page_size=20`);candidates.value=r.items;total.value=r.total;page.value=pageNumber}
async function loadChoices(pageNumber=choicePage.value){const r:Page<CaseChoice>=await request(`/cases?page=${pageNumber}&page_size=20`);choices.value=r.items;choiceTotal.value=r.total;choicePage.value=pageNumber}
async function move(delta:number){await run(async()=>{await load(page.value+delta)})}
async function moveChoices(delta:number){await run(async()=>{await loadChoices(choicePage.value+delta);target.value=''})}
async function create(){await run(async()=>{
 await command('person-case-candidate',`/person-drafts/${props.person.id}/case-candidates`,{case_id:target.value,person_version:personVersion.value,basis:basis.value})
 personVersion.value+=1;emit('updated',personVersion.value);target.value='';basis.value='';notice.value='候选关联已记录，身份与关系仍待核验'
 try{await load(1)}catch(e){if(isCancelled(e))throw e;error.value='关联已记录，但列表刷新失败。请重新查看，避免重复提交。'}
})}
async function revoke(candidate:Candidate){await run(async()=>{
 await command('person-case-revoke',`/person-drafts/case-candidates/${candidate.id}/revoke`,{version:candidate.version,reason:reason.value})
 revokeId.value='';reason.value='';notice.value='候选关联已撤销，历史保留'
 try{await load()}catch(e){if(isCancelled(e))throw e;error.value='撤销已成功，但列表刷新失败。请重新查看，避免重复提交。'}
})}
onMounted(()=>run(async()=>{await Promise.all([load(),loadChoices()])}))
</script>
<template>
<section class="detail"><h3>{{person.name}} · 候选案件</h3><p class="muted">仅记录待核查候选；不确认身份或案件人员关系，也不扩大案件访问范围。</p><button type="button" class="secondary" :disabled="loading" @click="emit('close')">关闭候选案件</button>
<div class="table-wrap"><table><thead><tr><th scope="col" class="row-number">序号</th><th>案件</th><th>依据</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="(c, rowIndex) in candidates" :key="c.id"><td class="row-number">{{(page-1)*20+rowIndex+1}}</td><td>{{c.case_number}} · {{c.case_title}}</td><td>{{c.basis}}</td><td>{{c.status==='ACTIVE' ? '待核查候选' : c.status==='REVOKED' ? '已撤销' : '未知状态'}}<span v-if="c.revoke_reason"> · {{c.revoke_reason}}</span></td><td><button v-if="c.status==='ACTIVE'" class="link" :disabled="loading" @click="revokeId=c.id;reason=''">撤销</button><form v-if="can('persons.write') && (revokeId===c.id)" @submit.prevent="revoke(c)"><label>撤销原因<input v-model="reason" required maxlength="1000"></label><p class="muted">人员、案件和候选历史均会保留。</p><button :disabled="loading">确认撤销候选</button> <button type="button" class="secondary" :disabled="loading" @click="revokeId=''">取消</button></form></td></tr></tbody></table><p v-if="!candidates.length" class="empty">暂无候选关联</p></div>
<Pagination :page="page" :total="total" :loading="loading" @change="move($event-page)" />
<h4>记录候选案件</h4><Pagination :page="choicePage" :total="choiceTotal" :loading="loading" @change="moveChoices($event-choicePage)" />
<form v-if="can('persons.write')" @submit.prevent="create"><label>本组织案件<select v-model="target" required><option value="" disabled>选择案件</option><option v-for="c in choices" :key="c.id" :value="c.id">{{c.number}} · {{c.title}}</option></select></label><label>候选依据<textarea v-model="basis" required maxlength="1000"></textarea></label><button :disabled="loading">记录待核查候选</button></form></section>
</template>
