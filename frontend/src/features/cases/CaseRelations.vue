<script setup lang="ts">
import Pagination from '../../shared/components/Pagination.vue'
const {can}=useWorkspace()
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useWorkspace } from '../../app/workspace'
import { createLatestRequests, isCancelled } from '../../shared/api/client'
type CaseChoice={id:string;number:string;title:string}
type Relation={id:string;other_case_number:string;other_case_title:string;relation_type:string;relation_status:string;basis:string;version:number;revoke_reason:string|null;created_at:string;created_by:string;revoked_at:string|null;revoked_by:string|null}
type Page<T>={items:T[];total:number}
const props=defineProps<{sourceCase:CaseChoice}>()
const emit=defineEmits<{close:[]}>()
const {api,loading,run,command,notice,error}=useWorkspace()
const pageRequests = createLatestRequests(api)
onBeforeUnmount(() => pageRequests.dispose())
const request = (path: string, options: RequestInit = {}) => pageRequests.latest(path.split('?')[0], path, options)
const relations=ref<Relation[]>([]),relationPage=ref(1),relationTotal=ref(0)
const choices=ref<CaseChoice[]>([]),choicePage=ref(1),choiceTotal=ref(0)
const target=ref(''),relationType=ref('RELATED_TO'),basis=ref(''),revokeId=ref(''),revokeReason=ref('')
const typeName:Record<string,string>={RELATED_TO:'关联',COOPERATE_WITH:'协办'}
async function loadRelations(page=relationPage.value){const r:Page<Relation>=await request(`/cases/${props.sourceCase.id}/relations?page=${page}&page_size=20`);relations.value=r.items;relationTotal.value=r.total;relationPage.value=page}
async function loadChoices(page=choicePage.value){const r:Page<CaseChoice>=await request(`/cases?page=${page}&page_size=20`);choices.value=r.items.filter(c=>c.id!==props.sourceCase.id);choiceTotal.value=r.total;choicePage.value=page}
async function moveRelations(delta:number){await run(async()=>{await loadRelations(relationPage.value+delta)})}
async function moveChoices(delta:number){await run(async()=>{await loadChoices(choicePage.value+delta);target.value=''})}
async function create(){await run(async()=>{
  await command('case-relation',`/cases/${props.sourceCase.id}/relations`,{target_case_id:target.value,relation_type:relationType.value,basis:basis.value})
  target.value='';basis.value='';notice.value='案件关系已记录；不代表并案'
  try{await loadRelations(1)}catch(e){if(isCancelled(e))throw e;error.value='关系已记录，但列表刷新失败。请重新查看，避免重复提交。'}
})}
async function revoke(rel:Relation){await run(async()=>{
  await command('case-relation-revoke',`/cases/relations/${rel.id}/revoke`,{version:rel.version,reason:revokeReason.value})
  revokeId.value='';revokeReason.value='';notice.value='案件关系已撤销，历史记录保留'
  try{await loadRelations()}catch(e){if(isCancelled(e))throw e;error.value='撤销已成功，但列表刷新失败。请重新查看，避免重复提交。'}
})}
onMounted(()=>run(async()=>{await Promise.all([loadRelations(),loadChoices()])}))
</script>
<template>
<section class="detail"><h3>{{sourceCase.number}} · 案件关系</h3><p class="muted">仅支持本组织案件之间的关联或协办，均不代表并案。撤销只影响关系，保留历史。</p><button type="button" class="secondary" :disabled="loading" @click="emit('close')">关闭关系</button>
<div class="table-wrap"><table><thead><tr><th scope="col" class="row-number">序号</th><th>另一案件</th><th>类型</th><th>状态</th><th>依据</th><th>操作</th></tr></thead><tbody><tr v-for="(rel, rowIndex) in relations" :key="rel.id"><td class="row-number">{{(relationPage-1)*20+rowIndex+1}}</td><td>{{rel.other_case_number}} · {{rel.other_case_title}}</td><td>{{typeName[rel.relation_type] || '未知类型'}}</td><td>{{rel.relation_status==='ACTIVE' ? '有效' : rel.relation_status==='REVOKED' ? '已撤销' : '未知状态'}}<span v-if="rel.revoke_reason"> · {{rel.revoke_reason}}</span></td><td>{{rel.basis}}</td><td><button v-if="rel.relation_status==='ACTIVE'" class="link" :disabled="loading" @click="revokeId=rel.id;revokeReason=''">撤销</button><form v-if="can('cases.write') && (revokeId===rel.id)" @submit.prevent="revoke(rel)"><label>撤销原因<input v-model="revokeReason" required maxlength="1000"></label><p class="muted">原案件及关系历史会保留。</p><button :disabled="loading">确认撤销关系</button> <button type="button" class="secondary" :disabled="loading" @click="revokeId=''">取消</button></form></td></tr></tbody></table><p v-if="!relations.length" class="empty">暂无案件关系</p></div>
<Pagination :page="relationPage" :total="relationTotal" :loading="loading" @change="moveRelations($event-relationPage)" />
<h4>记录案件关系</h4><p class="muted">从当前组织案件中选择；可以翻页。</p><Pagination :page="choicePage" :total="choiceTotal" :loading="loading" @change="moveChoices($event-choicePage)" />
<form v-if="can('cases.write')" @submit.prevent="create"><label>另一案件<select v-model="target" required><option value="" disabled>选择案件</option><option v-for="c in choices" :key="c.id" :value="c.id">{{c.number}} · {{c.title}}</option></select></label><label>关系类型<select v-model="relationType"><option value="RELATED_TO">关联</option><option value="COOPERATE_WITH">协办</option></select></label><label>关联依据<textarea v-model="basis" required maxlength="1000"></textarea></label><button :disabled="loading">记录关系</button></form></section>
</template>
