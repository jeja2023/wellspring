<script setup lang="ts">
import Pagination from '../../shared/components/Pagination.vue'
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useWorkspace } from '../../app/workspace'
import { createLatestRequests, isCancelled, RequestCancelled } from '../../shared/api/client'
import { fields } from './spreadsheet'
import { formatTimestamp } from '../../shared/time'
type Source={id:string;source_number:string;source_version:number;basis:string;created_case:boolean;created_by:string;created_at:string;source_hidden:boolean;status:string;version:number;revoke_reason:string|null}
const props=defineProps<{sourceCase:{id:string;number:string;title:string}}>()
const emit=defineEmits<{close:[]}>()
const {can,api,command,captureSession}=useWorkspace(),requests=createLatestRequests(api)
let mounted=true
onBeforeUnmount(()=>{mounted=false;requests.dispose()})
const rows=ref<Source[]>([]),page=ref(1),total=ref(0),busy=ref(false),error=ref(''),notice=ref('')
const snapshot=ref<{source_number:string;source_version:number;fields:Record<string,string|null>}|null>(null)
const revoking=ref<Source|null>(null),reason=ref('')
async function act(fn:()=>Promise<void>){const valid=captureSession();busy.value=true;error.value='';try{await fn()}catch(e){if(mounted&&valid()&&!isCancelled(e))error.value=e instanceof Error?e.message:'加载失败'}finally{busy.value=false}}
async function load(target=page.value){const valid=captureSession();const response=await requests.latest<{items:Source[];total:number}>('sources',`/cases/${props.sourceCase.id}/intake-sources?page=${target}&page_size=20`);if(!mounted||!valid())throw new RequestCancelled();rows.value=response.items;total.value=response.total;page.value=target}
function show(row:Source){const valid=captureSession();void act(async()=>{const response=await requests.latest<{source_number:string;source_version:number;fields:Record<string,string|null>}>('snapshot',`/cases/${props.sourceCase.id}/intake-sources/${row.id}`);if(!mounted||!valid())throw new RequestCancelled();snapshot.value=response})}
function revoke(){const valid=captureSession();const row=revoking.value;if(!row)return;void act(async()=>{await command(`intake-case-revoke-${row.id}`,`/cases/${props.sourceCase.id}/intake-sources/${row.id}/revoke`,{version:row.version,reason:reason.value});if(!mounted||!valid())throw new RequestCancelled();notice.value='来源关联已撤销；案件、接警原记录和历史快照均保留。';revoking.value=null;await load()})}
onMounted(()=>{void act(()=>load())})
</script>

<template>
  <section class="detail"><h3>{{sourceCase.number}} · 接警来源</h3><p class="muted">可关联多条接警信息。下方编号和快照为关联当时内容，原记录更改或隐藏不会覆盖历史。</p><button type="button" class="secondary" :disabled="busy" @click="emit('close')">关闭来源</button><p v-if="error" class="error" role="alert">{{error}} <button type="button" class="link" :disabled="busy" @click="act(()=>load())">重试</button></p><p v-if="notice" class="success" role="status">{{notice}}</p><div class="table-wrap"><table><thead><tr><th scope="col" class="row-number">序号</th><th>来源接警编号</th><th>关联方式 / 状态</th><th>办理人 / 时间</th><th>依据</th><th>操作</th></tr></thead><tbody><tr v-for="(row, rowIndex) in rows" :key="row.id"><td class="row-number">{{(page-1)*20+rowIndex+1}}</td><td>{{row.source_number}}<small v-if="row.source_hidden"><br>原记录已隐藏</small></td><td>{{row.created_case?'新建案件':'关联已有案件'}}<br>{{row.status==='ACTIVE'?'有效':'已撤销'}}</td><td>{{row.created_by}}<br>{{formatTimestamp(row.created_at)}}</td><td>{{row.basis}}<small v-if="row.revoke_reason"><br>撤销原因：{{row.revoke_reason}}</small></td><td><button class="link" :disabled="busy" @click="show(row)">来源快照</button><button v-if="row.status==='ACTIVE'&&can('cases.write')&&can('intake.write')" class="link" :disabled="busy" @click="revoking=row;reason=''">撤销关联</button></td></tr></tbody></table><p v-if="!rows.length&&!busy" class="empty">暂无接警来源，可从“接警信息”中明确关联。</p></div><Pagination :page="page" :total="total" :loading="busy" @change="act(()=>load($event))" />
    <form v-if="revoking" class="detail" @submit.prevent="revoke"><h4>撤销 {{revoking.source_number}} 的来源关联</h4><p>仅撤销关联；不会删除案件或接警信息，后续可重新核对并关联。</p><label>撤销依据<textarea v-model="reason" maxlength="1000" required></textarea></label><button :disabled="busy">确认撤销关联</button> <button type="button" class="secondary" :disabled="busy" @click="revoking=null">取消</button></form>
    <section v-if="snapshot" class="detail"><h4>来源快照：{{snapshot.source_number}} · 版本 {{snapshot.source_version}}</h4><button type="button" class="link" @click="snapshot=null">收起快照</button><dl class="case-detail-fields"><div v-for="field in fields" :key="field" class="case-detail-field"><dt>{{field}}</dt><dd>{{snapshot.fields[field]||'—'}}</dd></div></dl></section>
  </section>
</template>
