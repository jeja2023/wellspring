<script setup lang="ts">
import Pagination from '../../shared/components/Pagination.vue'
const {can}=useWorkspace()
import { formatTimestamp } from '../../shared/time'
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useWorkspace } from '../../app/workspace'
import { createLatestRequests, isCancelled } from '../../shared/api/client'
type Evidence={id:string;version:number}
type Custody={custodian_id:string;version:number}
type Handover={id:string;from_user_id:string;to_user_id:string;status:string;version:number;note:string;response_note:string|null;created_at:string;responded_at:string|null}
type Event={id:string;action:string;note:string;actor_id:string;created_at:string}
type Detail={current_user_id:string;custody:Custody|null;pending:Handover|null;events:{items:Event[];total:number;has_more:boolean}}
type Person={id:string;username:string}
const props=defineProps<{evidence:Evidence}>()
const {api,run,command,notice,error,loading,refreshEvidence}=useWorkspace()
const pageRequests = createLatestRequests(api)
onBeforeUnmount(() => pageRequests.dispose())
const request = (path: string, options: RequestInit = {}) => pageRequests.latest(path.split('?')[0], path, options)
const detail=ref<Detail|null>(null),people=ref<Person[]>([]),history=ref<Handover[]>([]),historyPage=ref(1),historyTotal=ref(0),page=ref(1),baselineNote=ref(''),target=ref(''),handoverNote=ref(''),responseNote=ref('')
const names:Record<string,string>={BASELINE:'登记基线',HANDOVER_PROPOSED:'发起交接',HANDOVER_ACCEPTED:'确认接收',HANDOVER_REJECTED:'拒收'}
const name=(id:string)=>people.value.find(p=>p.id===id)?.username ?? '本组织用户'
async function load(next=page.value){const result:Detail=await request(`/evidence/${props.evidence.id}/custody?page=${next}&page_size=20`);detail.value=result;page.value=next}
async function loadHistory(next=historyPage.value){const result:{items:Handover[];total:number}=await request(`/evidence/${props.evidence.id}/handovers?page=${next}&page_size=20`);history.value=result.items;historyTotal.value=result.total;historyPage.value=next}
async function moveHistory(delta:number){await run(async()=>{await loadHistory(historyPage.value+delta)})}
async function refresh(message:string,refreshItem=false){notice.value=message;try{await Promise.all([load(1),loadHistory(1),...(refreshItem?[refreshEvidence()]:[])])}catch(e){if(isCancelled(e))throw e;error.value='操作已记录，但刷新失败，请重新查看后再操作。'}}
async function baseline(){await run(async()=>{await command('custody-baseline',`/evidence/${props.evidence.id}/custody/baseline`,{evidence_version:props.evidence.version,note:baselineNote.value});baselineNote.value='';await refresh('开发保管基线已登记',true)})}
async function handover(){if(!detail.value?.custody)return;await run(async()=>{await command('custody-handover',`/evidence/${props.evidence.id}/handovers`,{custody_version:detail.value!.custody!.version,to_user_id:target.value,note:handoverNote.value});target.value='';handoverNote.value='';await refresh('交接已发起；原保管责任保持不变')})}
async function respond(action:'ACCEPT'|'REJECT'){if(!detail.value?.pending)return;await run(async()=>{const h=detail.value!.pending!;await command('custody-response',`/evidence/handovers/${h.id}/respond`,{version:h.version,action,note:responseNote.value});responseNote.value='';await refresh(action==='ACCEPT'?'接收已确认':'已拒收，原保管责任不变')})}
async function move(delta:number){await run(async()=>{await load(page.value+delta)})}
onMounted(()=>run(async()=>{const [_,__,users]=await Promise.all([load(1),loadHistory(1),request('/intelligence/assignees')]);people.value=users}))
</script>
<template>
<section v-if="detail" class="detail"><h3>保管与交接（开发验证）</h3><p class="muted">仅模拟本组织单件交接；不代表实物交接、封条核验或正式审批。</p>
<form v-if="!detail.custody" v-show="can('evidence.write')" @submit.prevent="baseline"><p>尚未登记开发保管基线；不会从旧数据推定保管人。</p><label>登记依据<input v-model="baselineNote" required maxlength="1000"></label><button :disabled="loading">登记本人为开发保管人</button></form>
<template v-else><p>当前保管人：{{name(detail.custody.custodian_id)}}</p><div v-if="detail.pending" class="warning"><p>待接收：{{name(detail.pending.from_user_id)}} → {{name(detail.pending.to_user_id)}}；交接说明：{{detail.pending.note}}</p><p>接收前原保管责任不变。</p><form v-if="detail.pending.to_user_id===detail.current_user_id" @submit.prevent="respond('ACCEPT')"><label>接收或拒收说明<input v-model="responseNote" required maxlength="1000"></label><button :disabled="loading">确认接收</button> <button type="button" class="secondary" :disabled="loading || !responseNote.trim()" @click="respond('REJECT')">拒收</button></form></div>
<form v-else-if="detail.custody.custodian_id===detail.current_user_id" @submit.prevent="handover"><label>接收人<select v-model="target" required><option value="" disabled>选择本组织接收人</option><option v-for="person in people.filter(p=>p.id!==detail?.current_user_id)" :key="person.id" :value="person.id">{{person.username}}</option></select></label><label>交接说明<input v-model="handoverNote" required maxlength="1000"></label><button :disabled="loading">发起交接</button><p class="muted">发起后由指定接收人确认，原保管责任不立即解除。</p></form></template>
<h4>交接记录</h4><div class="table-wrap"><table><thead><tr><th scope="col" class="row-number">序号</th><th>交出人</th><th>接收人</th><th>状态</th><th>交接说明</th><th>接收／拒收说明</th></tr></thead><tbody><tr v-for="(h, rowIndex) in history" :key="h.id"><td class="row-number">{{(historyPage-1)*20+rowIndex+1}}</td><td>{{name(h.from_user_id)}}</td><td>{{name(h.to_user_id)}}</td><td>{{({PENDING:'待接收',ACCEPTED:'已接收',REJECTED:'已拒收'} as Record<string,string>)[h.status] || '未知状态'}}</td><td>{{h.note}}</td><td>{{h.response_note || '—'}}</td></tr></tbody></table><p v-if="!history.length" class="muted">暂无交接记录</p></div><Pagination :page="historyPage" :total="historyTotal" :loading="loading" @change="moveHistory($event-historyPage)" /><h4>保管事件</h4><ul><li v-for="event in detail.events.items" :key="event.id">{{names[event.action] || '未知事件'}} · {{name(event.actor_id)}} · {{event.note}} · {{formatTimestamp(event.created_at)}}</li></ul><p v-if="!detail.events.items.length" class="muted">暂无保管事件</p><Pagination :page="page" :total="detail.events.total" :loading="loading" :has-more="detail.events.has_more" @change="move($event-page)" /></section>
</template>
