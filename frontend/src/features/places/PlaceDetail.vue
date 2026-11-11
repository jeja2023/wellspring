<script setup lang="ts">
import {onBeforeUnmount,onMounted,ref} from 'vue'
import {useWorkspace} from '../../app/workspace'
import {createLatestRequests,isCancelled} from '../../shared/api/client'
import Pagination from '../../shared/components/Pagination.vue'
import {formatTimestamp} from '../../shared/time'
import PlaceEditor from './PlaceEditor.vue'
import PlaceRecordEditor from './PlaceRecordEditor.vue'
import PlaceActionDialog from './PlaceActionDialog.vue'
import {actions,kinds,statuses,today,type ActionSpec,type History,type Incident,type Inspection,type Page,type Place} from './types'
const props=defineProps<{placeId:string}>(),emit=defineEmits<{close:[]}>()
const {api,can,openMap,page:workspacePage}=useWorkspace(),queries=createLatestRequests(api)
const place=ref<Place>(),tab=ref<'inspections'|'incidents'|'history'>('inspections'),records=ref<Page<Inspection|Incident|History>>({items:[],total:0,page:1})
const busy=ref(false),error=ref(''),editing=ref(false),recordEditor=ref<'inspection'|'incident'|''>(''),editingIncident=ref<Incident>(),action=ref<ActionSpec|null>(null),detail=ref<Incident|null>(null)
let alive=true;onBeforeUnmount(()=>{alive=false;queries.dispose()})
async function act(task:()=>Promise<void>){if(busy.value)return;busy.value=true;error.value='';try{await task()}catch(e){if(alive&&!isCancelled(e))error.value=e instanceof Error?e.message:'查询失败'}finally{if(alive)busy.value=false}}
async function load(area=tab.value,target=1){const [p,result]=await Promise.all([queries.latest<Place>('place',`/places/${props.placeId}`),queries.latest<Page<Inspection|Incident|History>>('records',`/places/${props.placeId}/${area}?page=${target}`)]);place.value=p;records.value=result;tab.value=area;detail.value=null}
function afterSave(){action.value=null;editing.value=false;recordEditor.value='';editingIncident.value=undefined;void act(()=>load())}
function state(){const row=place.value;if(row)action.value={title:row.active?'停用场所':'启用场所',path:`/places/${row.id}/state`,version:row.version,extra:{active:!row.active}}}
function complete(row:Inspection){action.value={title:'记录整改复查结果',path:`/places/inspections/${row.id}/complete`,version:row.version}}
function transition(row:Incident,code:string,title:string){action.value={title,path:`/places/incidents/${row.id}/transition`,version:row.version,extra:{action:code}}}
function clue(row:Incident){action.value={title:'转录线索草稿',path:`/places/incidents/${row.id}/clue`,version:row.version}}
function editIncident(row:Incident){editingIncident.value=row;recordEditor.value='incident'}
onMounted(()=>{void act(()=>load())})
</script>
<template><div v-if="place" class="place-detail">
  <p v-if="error" class="error" role="alert">{{error}}</p><section class="card"><div class="place-detail-header"><div><h2>{{place.name}}</h2><p class="muted">{{place.code}} · {{kinds[place.kind]}} · {{place.active?'管理中':'已停用'}}</p></div><div class="actions"><button v-if="can('geography.read')" class="secondary" @click="openMap('PLACE',place.id)">地图定位</button><button v-if="can('places.write')" class="secondary" :disabled="busy" @click="editing=true">更正资料</button><button v-if="can('places.write')" class="link" :disabled="busy" @click="state">{{place.active?'停用':'启用'}}</button><button class="link" @click="emit('close')">返回台账</button></div></div>
  <div class="place-facts"><p><small>区域 / 地址</small>{{place.district}} · {{place.address}}</p><p><small>责任岗位 / 承办人</small>{{place.responsible}}</p><p><small>纳入管理依据</small>{{place.management_basis}}</p><p><small>管理复核日期</small><span :class="{'place-overdue':place.review_on&&place.review_on<today()}">{{place.review_on||'未指定'}}{{place.review_on&&place.review_on<today()?' · 已到期，待人工复核':''}}</span></p><p><small>待完成整改</small>{{place.open_inspections||0}} 项</p><p><small>未办结事件</small>{{place.open_incidents||0}} 条</p></div></section>
  <div class="place-tabs" role="tablist" aria-label="场所业务记录"><button v-for="item in ([['inspections','巡查整改'],['incidents','事件处置'],['history','历史记录']] as const)" :key="item[0]" role="tab" :aria-selected="tab===item[0]" :class="{secondary:tab!==item[0]}" :disabled="busy" @click="act(()=>load(item[0]))">{{item[1]}}</button></div>
  <section class="card"><div class="place-toolbar"><p class="muted">{{tab==='inspections'?'巡查事实和整改复查分别留痕':tab==='incidents'?'事件先核验，处置反馈经独立复核后办结':'历次资料、巡查及事件办理记录'}}</p><button v-if="can('places.write')&&place.active&&tab!=='history'" :disabled="busy" @click="editingIncident=undefined;recordEditor=tab==='inspections'?'inspection':'incident'">{{tab==='inspections'?'登记巡查':'登记事件'}}</button></div>
    <div v-if="tab==='inspections'" class="table-wrap"><table aria-label="场所巡查记录"><thead><tr><th scope="col" class="row-number">序号</th><th>巡查日期</th><th>现场情况</th><th>整改期限</th><th>状态 / 复查</th><th>操作</th></tr></thead><tbody><tr v-for="(row,index) in (records.items as Inspection[])" :key="row.id"><td class="row-number">{{(records.page-1)*20+index+1}}</td><td>{{row.inspected_on}}</td><td class="place-text">{{row.findings}}</td><td :class="{'place-overdue':row.status==='OPEN'&&row.due_on&&row.due_on<today()}">{{row.due_on||'—'}}{{row.status==='OPEN'&&row.due_on&&row.due_on<today()?' · 逾期':''}}</td><td>{{row.status==='OPEN'?'待整改复查':'已完成'}}<p v-if="row.result_note">{{row.result_note}}</p></td><td><button v-if="can('places.write')&&row.status==='OPEN'" class="link" :disabled="busy" @click="complete(row)">记录复查</button></td></tr></tbody></table></div>
    <div v-else-if="tab==='incidents'" class="table-wrap"><table aria-label="场所事件记录"><thead><tr><th scope="col" class="row-number">序号</th><th>事件标题 / 时间</th><th>来源</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="(row,index) in (records.items as Incident[])" :key="row.id"><td class="row-number">{{(records.page-1)*20+index+1}}</td><td>{{row.title}}<br><small>{{formatTimestamp(row.occurred_at)}}</small></td><td>{{row.source}}</td><td>{{statuses[row.status]}}<br><small v-if="row.clue_id">已转录线索草稿</small></td><td><button class="link" :disabled="busy" @click="detail=row">查看事件</button><button v-if="can('geography.read')" class="link" @click="openMap('INCIDENT',row.id)">事件定位</button></td></tr></tbody></table></div>
    <ol v-else class="place-history-list"><li v-for="row in (records.items as History[])" :key="row.id"><strong>{{actions[row.action]||row.action}}</strong> · <small>{{formatTimestamp(row.created_at)}}</small><p>{{row.note}}</p><details><summary>查看该次记录</summary><pre>{{JSON.stringify(row.snapshot,null,2)}}</pre></details></li></ol>
    <p v-if="!records.items.length&&!busy" class="empty">暂无记录</p><Pagination :page="records.page" :total="records.total" :loading="busy" @change="act(()=>load(tab,$event))"/>
  </section>
  <section v-if="detail" class="card"><div class="place-toolbar"><h2>{{detail.title}}</h2><button class="link" @click="detail=null">收起事件</button></div><div class="place-record-summary"><p><small>具体事实</small><br>{{detail.facts}}</p><p><small>资料引用</small><br>{{detail.material_ref}}</p><p v-if="detail.disposition"><small>处置反馈</small><br>{{detail.disposition}}</p><span class="tag">{{statuses[detail.status]}}</span></div><div class="map-form-actions">
    <button v-if="can('places.write')&&['DRAFT','RETURNED'].includes(detail.status)" :disabled="busy" @click="editIncident(detail)">补充资料</button>
    <button v-if="can('places.review')&&detail.status==='DRAFT'" :disabled="busy" @click="transition(detail,'CONFIRM','核验确认事件')">核验确认</button>
    <button v-if="can('places.review')&&['DRAFT','SUBMITTED'].includes(detail.status)" class="secondary" :disabled="busy" @click="transition(detail,'RETURN','退回补充资料')">退回补充</button>
    <button v-if="can('places.write')&&detail.status==='OPEN'" :disabled="busy" @click="transition(detail,'SUBMIT','提交事件处置反馈')">提交处置反馈</button>
    <button v-if="can('places.review')&&detail.status==='SUBMITTED'" :disabled="busy" @click="transition(detail,'CLOSE','复核事件并办结')">复核办结</button>
    <button v-if="can('places.review')&&detail.status==='CLOSED'" class="secondary" :disabled="busy" @click="transition(detail,'REOPEN','重新办理事件')">重新办理</button>
    <button v-if="can('places.write')&&can('intelligence.read')&&can('intelligence.write')&&!detail.clue_id&&['OPEN','SUBMITTED','CLOSED'].includes(detail.status)" class="secondary" :disabled="busy" @click="clue(detail)">转录线索草稿</button>
    <button v-if="detail.clue_id&&can('intelligence.read')" class="link" @click="workspacePage='情报线索'">前往情报线索</button>
  </div></section>
  <PlaceEditor v-if="editing" :place="place" @close="editing=false" @saved="afterSave"/>
  <PlaceRecordEditor v-if="recordEditor" :place-id="place.id" :kind="recordEditor" :incident="editingIncident" @close="recordEditor=''" @saved="afterSave"/>
  <PlaceActionDialog v-if="action" :spec="action" @close="action=null" @saved="afterSave"/>
</div><p v-else-if="error" class="error" role="alert">{{error}}</p><p v-else role="status">正在加载场所资料…</p></template>
