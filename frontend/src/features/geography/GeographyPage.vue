<script setup lang="ts">
import {computed,nextTick,onBeforeUnmount,onMounted,reactive,ref} from 'vue'
import {useWorkspace} from '../../app/workspace'
import {createLatestRequests,isCancelled,RequestCancelled} from '../../shared/api/client'
import Pagination from '../../shared/components/Pagination.vue'
import {formatTimestamp} from '../../shared/time'
import BusinessMap from './BusinessMap.vue'
import {layerColors,layerNames,type GeoResource,type MapConfig,type MapPoints,type Page,type ResourceType} from './types'
import './geography.css'
const {api,command,can,captureSession,geographyFocus,openPlace,page:workspacePage}=useWorkspace(),queries=createLatestRequests(api)
const config=ref<MapConfig>(),points=ref<MapPoints>({items:[],total:0,truncated:false,limit:500}),listing=ref<Page<GeoResource>>({items:[],page:1,total:0})
const map=ref<InstanceType<typeof BusinessMap>>(),selected=ref<GeoResource|null>(null),editing=ref(false),missingTiles=ref(false)
const busy=ref(false),error=ref(''),notice=ref(''),applied=ref({layer:'ALL',keyword:'',located:null as boolean|null,bbox:undefined as [number,number,number,number]|undefined})
const form=reactive({layer:'ALL',keyword:'',located:''}),coordinates=reactive({longitude:'',latitude:'',source:'',version:0})
const history=ref<Page<{id:string;created_at:string;snapshot:{longitude:number|null;latitude:number|null;source:string;version:number}}>|null>(null)
let alive=true
onBeforeUnmount(()=>{alive=false;queries.dispose()})
function ensure(valid:()=>boolean){if(!alive||!valid())throw new RequestCancelled()}
async function act(task:()=>Promise<void>){if(busy.value)return;busy.value=true;error.value='';notice.value='';try{await task()}catch(e){if(!isCancelled(e)&&alive)error.value=e instanceof Error?e.message:'操作失败'}finally{if(alive)busy.value=false}}
async function load(target=1,filter=applied.value,fit=false){
  const [list,result]=await Promise.all([
    queries.latest<Page<GeoResource>>('list','/geography/search',{method:'POST',body:JSON.stringify({...filter,page:target})}),
    queries.latest<MapPoints>('points','/geography/points',{method:'POST',body:JSON.stringify(filter)}),
  ])
  listing.value=list;points.value=result;applied.value={...filter};if(fit){await nextTick();map.value?.fit()}
}
function filter(){return {layer:form.layer,keyword:form.keyword.trim(),located:form.located===''?null:form.located==='yes',bbox:undefined}}
function search(){void act(async()=>{await load(1,filter(),true);selected.value=null;editing.value=false;history.value=null})}
function range(){const bbox=map.value?.bounds();if(bbox)void act(()=>load(1,{...applied.value,bbox}))}
async function select(row:GeoResource){if(busy.value||editing.value)return;await act(async()=>{const detail=await queries.latest<GeoResource>('selected',`/geography/${row.resource_type}/${row.resource_id}`);selected.value={...row,...detail};history.value=null;map.value?.focus(selected.value)})}
const canEdit=computed(()=>selected.value&&can('geography.write')&&can((selected.value.resource_type==='WASTEWATER'?'wastewater':'places')+'.write'))
function edit(){const row=selected.value;if(!row)return;Object.assign(coordinates,{longitude:row.longitude===null?'':String(row.longitude),latitude:row.latitude===null?'':String(row.latitude),source:row.source,version:row.version});editing.value=true;history.value=null;notice.value='可在地图点击选点，也可输入 WGS84 经纬度。'}
function pick(longitude:number,latitude:number){if(editing.value){coordinates.longitude=String(longitude);coordinates.latitude=String(latitude)}}
function save(){const row=selected.value;if(!row)return;void act(async()=>{
  const valid=captureSession(),result=await command(`map-location-${row.resource_type}-${row.resource_id}`,`/geography/${row.resource_type}/${row.resource_id}/location`,{
    version:coordinates.version,longitude:coordinates.longitude===''?null:Number(coordinates.longitude),latitude:coordinates.latitude===''?null:Number(coordinates.latitude),source:coordinates.source,coordinate_system:'WGS84',
  }) as GeoResource;ensure(valid);selected.value={...row,...result};editing.value=false;notice.value='坐标已保存并记录历史。'
  try{await load();if(result.longitude!==null)map.value?.focus(selected.value)}catch(e){if(isCancelled(e))throw e;error.value='坐标已保存，列表刷新失败，请重新查询。'}
})}
function showHistory(target=1){const row=selected.value;if(!row)return;void act(async()=>{history.value=await queries.latest('history',`/geography/${row.resource_type}/${row.resource_id}/history?page=${target}`)})}
function openBusiness(){const row=selected.value;if(!row)return;if(row.resource_type==='WASTEWATER')workspacePage.value='污水监测';else if(row.place_id)openPlace(row.place_id)}
onMounted(()=>{void act(async()=>{
  config.value=await queries.latest<MapConfig>('config','/geography/config');await load(1,applied.value,true)
  const focus=geographyFocus.value;geographyFocus.value=null
  if(focus){const row=await queries.latest<GeoResource>('selected',`/geography/${focus.type}/${focus.id}`);selected.value=row;map.value?.focus(row)}
})})
</script>
<template><div class="geography-page">
  <p v-if="error" role="alert" class="error">{{error}}</p><p v-if="notice" role="status" class="success">{{notice}}</p>
  <section class="card map-intro"><div><strong>业务空间分布</strong><p class="muted">按获准图层查看场所、具体事件和采样点；坐标与来源可独立更正留痕。</p></div><span class="tag">{{config?.tiles_available?'离线底图':'坐标视图'}} · WGS84</span></section>
  <form class="card map-filters" @submit.prevent="search"><label>业务图层<select v-model="form.layer" :disabled="busy||editing"><option value="ALL">全部获准图层</option><option v-for="layer in config?.layers||[]" :key="layer" :value="layer">{{layerNames[layer]}}</option></select></label><label>查找点位<input v-model="form.keyword" maxlength="100" placeholder="名称、编号或地址" :disabled="editing"></label><label>坐标状态<select v-model="form.located" :disabled="busy||editing"><option value="">全部记录</option><option value="yes">已定位</option><option value="no">未定位</option></select></label><button :disabled="busy||editing">查询</button></form>
  <p v-if="config&&!config.tiles_available" class="map-basemap-note" role="status">尚未接入离线底图，当前显示经纬度网格；道路和地名将在底图接入后显示。</p>
  <p v-else-if="missingTiles" class="map-basemap-note" role="status">当前范围缺少离线底图瓦片，已显示坐标网格，业务点位仍可查看。</p>
  <div class="map-layout"><section class="card map-panel"><div class="map-toolbar"><span>已显示 {{points.items.length}} / {{points.total}} 个定位结果{{applied.bbox?' · 当前范围':''}}</span><div><button type="button" class="secondary" :disabled="busy||editing" @click="range">查询当前范围</button><button type="button" class="secondary" :disabled="busy||editing" @click="act(()=>load(1,{...applied,bbox:undefined},true))">显示全部结果</button><button type="button" class="link" @click="map?.fit()">适配点位</button></div></div>
    <p v-if="points.truncated" class="map-basemap-note" role="status">结果超过 {{points.limit}} 个，请缩小地图范围或筛选图层后查询；当前显示部分点位。</p>
    <BusinessMap v-if="config" ref="map" :points="points.items" :tiles="config.tiles_available" :selecting="editing&&!busy" @select="select" @pick="pick" @coverage="missingTiles=$event"/>
    <div class="map-legend"><span v-for="layer in config?.layers||[]" :key="layer"><i :style="{background:layerColors[layer]}"></i>{{layerNames[layer]}}</span><span>相邻点位聚合显示，点击数字展开</span><span v-if="config?.tiles_available">{{config.attribution}}</span></div>
  </section><section class="card map-sidebar">
    <template v-if="selected"><div class="map-sidebar-title"><h2>{{selected.name}}</h2><button type="button" class="link" :disabled="busy||editing" @click="selected=null;history=null">返回列表</button></div><p class="muted">{{layerNames[selected.resource_type]}}</p><p v-if="selected.address">{{selected.address}}</p>
      <form v-if="editing" class="map-coordinate-editor" @submit.prevent="save"><p class="map-basemap-note">在地图点击选点；确认坐标来源为 WGS84。清除经纬度可移除误标。</p><label>经度<input v-model="coordinates.longitude" type="number" min="-180" max="180" step="0.000001" :required="coordinates.latitude!==''" :disabled="busy"></label><label>纬度<input v-model="coordinates.latitude" type="number" min="-85" max="85" step="0.000001" :required="coordinates.longitude!==''" :disabled="busy"></label><label>坐标来源 / 更正说明<textarea v-model="coordinates.source" maxlength="500" required :disabled="busy"></textarea></label><div class="map-form-actions"><button :disabled="busy">保存坐标</button><button type="button" class="secondary" :disabled="busy" @click="editing=false">取消</button><button type="button" class="link" :disabled="busy" @click="coordinates.longitude='';coordinates.latitude='';coordinates.source=''">清除误标</button></div></form>
      <template v-else><dl class="map-coordinate-summary"><dt>经度 / 纬度</dt><dd>{{selected.longitude===null?'未定位':selected.longitude+' / '+selected.latitude}}</dd><dt>坐标来源</dt><dd>{{selected.source||'尚未登记'}}</dd></dl><div class="map-form-actions"><button v-if="canEdit" :disabled="busy" @click="edit">{{selected.longitude===null?'补录坐标':'修改坐标'}}</button><button class="secondary" :disabled="busy" @click="openBusiness">查看业务</button><button class="link" :disabled="busy" @click="showHistory()">坐标历史</button></div></template>
      <div v-if="history" class="map-history"><h3>坐标历史</h3><ol><li v-for="item in history.items" :key="item.id"><strong>第 {{item.snapshot.version}} 版 · {{item.snapshot.longitude===null?'已清除':item.snapshot.longitude+' / '+item.snapshot.latitude}}</strong><p>{{item.snapshot.source}}</p><small>{{formatTimestamp(item.created_at)}}</small></li></ol><p v-if="!history.items.length" class="muted">暂无坐标变更</p><Pagination :page="history.page" :total="history.total" :loading="busy" @change="showHistory"/></div>
    </template><template v-else><h2>业务记录 <small>{{listing.total}} 条</small></h2><p class="muted">未定位记录可在此补录坐标。</p><ul class="map-resource-list"><li v-for="row in listing.items" :key="row.resource_type+row.resource_id"><button type="button" :disabled="busy" @click="select(row)"><span><i :style="{background:layerColors[row.resource_type]}"></i>{{row.name}}</span><small>{{layerNames[row.resource_type]}} · {{row.longitude===null?'未定位':'已定位'}}</small><small>{{row.code||row.address}}</small></button></li></ul><p v-if="!listing.items.length&&!busy" class="empty">暂无符合条件的记录</p><Pagination :page="listing.page" :total="listing.total" :loading="busy" @change="act(()=>load($event))"/></template>
  </section></div>
</div></template>
