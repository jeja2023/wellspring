<script setup lang="ts">
import {onBeforeUnmount,onMounted,reactive,ref} from 'vue'
import {useWorkspace} from '../../app/workspace'
import {createLatestRequests,isCancelled} from '../../shared/api/client'
import Pagination from '../../shared/components/Pagination.vue'
import StatusBadge from '../../shared/components/StatusBadge.vue'
import PlaceDetail from './PlaceDetail.vue'
import PlaceEditor from './PlaceEditor.vue'
import {kinds,today,type Page,type Place} from './types'
import '../geography/geography.css'
const {api,can,openMap,placeFocus,page:workspacePage,takeWorkbenchFocus}=useWorkspace(),queries=createLatestRequests(api)
const listing=ref<Page<Place>>({items:[],page:1,total:0}),busy=ref(false),error=ref(''),creating=ref(false),selected=ref(''),focusTab=ref<'inspections'|'incidents'>('inspections'),focusRecord=ref('')
const form=reactive({keyword:'',kind:'',active:''}),applied=ref({keyword:'',kind:null as string|null,active:null as boolean|null})
let alive=true;onBeforeUnmount(()=>{alive=false;queries.dispose()})
async function load(target=1,filter=applied.value){busy.value=true;error.value='';try{const result=await queries.latest<Page<Place>>('places','/places/search',{method:'POST',body:JSON.stringify({...filter,page:target})});listing.value=result;applied.value={...filter}}catch(e){if(alive&&!isCancelled(e))error.value=e instanceof Error?e.message:'查询失败'}finally{if(alive)busy.value=false}}
function search(){void load(1,{keyword:form.keyword.trim(),kind:form.kind||null,active:form.active===''?null:form.active==='yes'})}
function saved(row:Place){creating.value=false;selected.value=row.id}
function back(){selected.value='';void load()}
onMounted(()=>{const focus=takeWorkbenchFocus('places');if(focus){selected.value=focus.resource_id;focusTab.value=focus.tab==='incidents'?'incidents':'inspections';focusRecord.value=focus.id}else if(placeFocus.value){selected.value=placeFocus.value;placeFocus.value=''}else void load()})
</script>
<template><div class="places-page"><PlaceDetail v-if="selected" :key="selected" :place-id="selected" :initial-tab="focusTab" :focus-id="focusRecord" @close="back"/><template v-else>
  <p v-if="error" role="alert" class="error">{{error}}</p><section class="card map-intro"><div><strong>场所台账与处置</strong><p class="muted">登记管理依据，记录巡查整改与具体事件，跟踪核验和处置反馈。</p></div><div class="map-form-actions"><button v-if="can('geography.read')" class="secondary" @click="workspacePage='业务地图'">地图查看</button><button v-if="can('places.write')" :disabled="busy" @click="creating=true">新增场所</button></div></section>
  <form class="card map-filters" @submit.prevent="search"><label>查找场所<input v-model="form.keyword" maxlength="100" placeholder="名称、编号或地址"></label><label>场所类型<select v-model="form.kind"><option value="">全部类型</option><option v-for="(name,key) in kinds" :key="key" :value="key">{{name}}</option></select></label><label>管理状态<select v-model="form.active"><option value="">全部状态</option><option value="yes">管理中</option><option value="no">已停用</option></select></label><button :disabled="busy">查询</button></form>
  <section class="card"><div class="table-wrap"><table class="table-nowrap" aria-label="重点场所台账"><thead><tr><th scope="col" class="row-number">序号</th><th>场所编号</th><th>场所名称</th><th>类型</th><th>所属区域</th><th>场所地址</th><th>责任岗位</th><th>复核日期</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="(row,index) in listing.items" :key="row.id"><td class="row-number">{{(listing.page-1)*20+index+1}}</td><td>{{row.code}}</td><td>{{row.name}}</td><td>{{kinds[row.kind]}}</td><td>{{row.district}}</td><td>{{row.address}}</td><td>{{row.responsible}}</td><td :class="{'place-overdue':row.active&&row.review_on&&row.review_on<today()}">{{row.review_on||'未指定'}}{{row.active&&row.review_on&&row.review_on<today()?' · 待复核':''}}</td><td><StatusBadge :tone="row.active?'success':'neutral'">{{row.active?'管理中':'已停用'}}</StatusBadge></td><td><button class="link" :disabled="busy" @click="focusTab='inspections';focusRecord='';selected=row.id">查看场所</button><button v-if="can('geography.read')" class="link" @click="openMap('PLACE',row.id)">地图定位</button></td></tr></tbody></table><p v-if="!listing.items.length&&!busy" class="empty">暂无符合条件的场所</p></div><Pagination :page="listing.page" :total="listing.total" :loading="busy" @change="load($event)"/></section>
  <PlaceEditor v-if="creating" @close="creating=false" @saved="saved"/>
</template></div></template>
