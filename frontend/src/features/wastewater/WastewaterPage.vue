<script setup lang="ts">
import Pagination from '../../shared/components/Pagination.vue'
const {can,openMap}=useWorkspace()
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useWorkspace } from '../../app/workspace'
import { createLatestRequests, isCancelled, RequestCancelled } from '../../shared/api/client'
import { formatTimestamp } from '../../shared/time'
import './wastewater.css'
import FormDialog from '../../shared/components/FormDialog.vue'
const editor=ref<'sites'|'samples'|'results'|''>('')

type Area = 'sites' | 'samples' | 'results'
type Site = { id:string; code:string; name:string; district:string; plant_name:string; catchment:string; active:boolean; state_note:string; version:number }
type Sample = { id:string; code:string; site_id:string; site_name:string; sampled_at:string; sampling_method:string; collector:string; quality:string; flow_m3_day:string|null; note:string }
type ResultFields = { analyte:string; detection:string; concentration:string|null; quantification_limit:string|null; laboratory:string; analysis_method:string; report_number:string; note:string }
type LabResult = ResultFields & { id:string; sample_id:string; sample_code:string; sampled_at:string; site_name:string; author:string; created_by:string; state:string; version:number; review_note:string }
type Point = { result_id:string; sample_code:string; sampled_at:string; detection:string; concentration:string|null; quantification_limit:string|null }
type TrendResult = { site_name:string; unit:string; points:Point[]; sample_count:number; quantified_count:number; basis:string }
type Event = { id:string; actor:string; action:string; note:string; created_at:string; snapshot:ResultFields }
type Page<T> = { items:T[]; page:number; total:number; current_user_id?:string }
const { api, command, captureSession,takeWorkbenchFocus,quickCreate } = useWorkspace()
const queries = createLatestRequests(api)
let mounted = true
onBeforeUnmount(() => { mounted = false; queries.dispose() })
const tab = ref<Area|'trends'>('sites'), pending = ref(0), error = ref(''), notice = ref('')
const busy = computed(() => pending.value > 0)
const sites = ref<Site[]>([]), samples = ref<Sample[]>([]), results = ref<LabResult[]>([])
const page = reactive<Record<Area, {page:number; total:number; keyword:string}>>({ sites:{page:1,total:0,keyword:''}, samples:{page:1,total:0,keyword:''}, results:{page:1,total:0,keyword:''} })
const keyword = ref(''), currentUserId = ref('')
const siteChoices = ref<Site[]>([]), sampleChoices = ref<{id:string;code:string}[]>([])
const chosenSite = ref<Site|null>(null), chosenSample = ref<{id:string;code:string}|null>(null)
const selectableSites = computed(() => [...new Map([...siteChoices.value, ...(chosenSite.value ? [chosenSite.value] : [])].map(row=>[row.id,row])).values()])
const selectableSamples = computed(() => [...new Map([...sampleChoices.value, ...(chosenSample.value ? [chosenSample.value] : [])].map(row=>[row.id,row])).values()])
const siteForm = reactive({code:'',name:'',district:'',plant_name:'',catchment:''})
const sampleForm = reactive({code:'',site_id:'',sampled_at:'',sampling_method:'COMPOSITE',collector:'',flow_m3_day:'',quality:'VALID',note:''})
const emptyResult = ():ResultFields => ({analyte:'',detection:'QUANTIFIED',concentration:'',quantification_limit:'',laboratory:'',analysis_method:'',report_number:'',note:''})
const resultForm = reactive({...emptyResult(),sample_id:''})
const editing = ref<LabResult|null>(null), reviewing = ref<LabResult|null>(null), reviewNote = ref('')
const stateSite = ref<Site|null>(null), stateReason = ref('')
const history = ref<Event[]>([]), historyTitle = ref('')
const detectionNames:Record<string,string> = {QUANTIFIED:'定量检出',BELOW_LOQ:'低于定量限',NOT_DETECTED:'未检出'}
const stateNames:Record<string,string> = {DRAFT:'待复核',RETURNED:'已退回',REVIEWED:'已复核'}
const methodNames:Record<string,string> = {GRAB:'瞬时采样',COMPOSITE:'混合采样'}
const actionNames:Record<string,string> = {CREATE:'录入',UPDATE:'修订',CONFIRM:'确认',RETURN:'退回'}
function ensure(valid:()=>boolean) { if (!mounted || !valid()) throw new RequestCancelled() }
async function run(fn:(check:()=>void)=>Promise<void>) {
  const valid=captureSession();pending.value++;error.value='';notice.value=''
  try {await fn(()=>ensure(valid))} catch(e) {if(mounted&&valid()&&!isCancelled(e))error.value=e instanceof Error?e.message:'操作未完成'}
  finally {pending.value--}
}
async function load(area:Area,target=page[area].page,term=page[area].keyword) {
  const valid=captureSession()
  const response=await queries.latest<Page<Site|Sample|LabResult>>(area,`/wastewater/${area}/search`,{method:'POST',body:JSON.stringify({keyword:term,page:target,page_size:20})})
  ensure(valid)
  if(area==='sites')sites.value=response.items as Site[]
  if(area==='samples')samples.value=response.items as Sample[]
  if(area==='results'){results.value=response.items as LabResult[];currentUserId.value=response.current_user_id||''}
  page[area]={page:target,total:response.total,keyword:term}
}
async function choices() {
  const valid=captureSession()
  const [a,b]=await Promise.all([queries.latest<Page<Site>>('site-choices','/wastewater/sites/search',{method:'POST',body:JSON.stringify({page_size:100})}),queries.latest<Page<Sample>>('sample-choices','/wastewater/samples/search',{method:'POST',body:JSON.stringify({page_size:100})})])
  ensure(valid);siteChoices.value=a.items;sampleChoices.value=b.items
}
function changeTab(value:Area|'trends') {tab.value=value;keyword.value=value==='trends'?'':page[value].keyword;void run(async check=>{await choices();check();if(value!=='trends')await load(value)})}
async function refreshSaved(area:Area,message:string) {
  editor.value='';notice.value=message
  try {await Promise.all([load(area),choices()])} catch(e){if(isCancelled(e))throw e;error.value='操作已保存，但列表刷新失败。请重新查询，避免重复提交。'}
}
function addSite(){void run(async check=>{const row=await command('wastewater-site','/wastewater/sites',{...siteForm}) as Site;check();chosenSite.value=row;sampleForm.site_id=row.id;Object.assign(siteForm,{code:'',name:'',district:'',plant_name:'',catchment:''});await refreshSaved('sites','采样点已登记')})}
function setState(){const row=stateSite.value;if(!row)return;void run(async check=>{await command(`wastewater-site-state-${row.id}`,`/wastewater/sites/${row.id}/state`,{version:row.version,active:!row.active,reason:stateReason.value});check();stateSite.value=null;stateReason.value='';await refreshSaved('sites','点位状态已更新，历史样本保留')})}
function chooseSite(row:Site){editor.value='samples';chosenSite.value=row;sampleForm.site_id=row.id;changeTab('samples')}
function chooseTrendSite(row:Site){chosenSite.value=row;trendForm.site_id=row.id;changeTab('trends')}
function addSample(){void run(async check=>{
  // datetime-local is explicitly interpreted in the product's displayed China timezone.
  await command('wastewater-sample','/wastewater/samples',{...sampleForm,sampled_at:`${sampleForm.sampled_at.length===16?sampleForm.sampled_at+':00':sampleForm.sampled_at}+08:00`,flow_m3_day:sampleForm.flow_m3_day||null});check()
  sampleForm.code='';sampleForm.note='';await refreshSaved('samples','采样记录已保存')
})}
function chooseSample(row:{id:string;code:string}){editor.value='results';chosenSample.value=row;editing.value=null;Object.assign(resultForm,emptyResult(),{sample_id:row.id});changeTab('results')}
function editResult(row:LabResult){error.value='';editor.value='results';editing.value=row;chosenSample.value={id:row.sample_id,code:row.sample_code};Object.assign(resultForm,{...row,sample_id:row.sample_id,concentration:row.concentration||'',quantification_limit:row.quantification_limit||''})}
function clearResult(){editing.value=null;Object.assign(resultForm,emptyResult(),{sample_id:''})}
function saveResult(){void run(async check=>{
  const fields={analyte:resultForm.analyte,detection:resultForm.detection,concentration:resultForm.detection==='QUANTIFIED'?resultForm.concentration||null:null,quantification_limit:resultForm.quantification_limit||null,laboratory:resultForm.laboratory,analysis_method:resultForm.analysis_method,report_number:resultForm.report_number,note:resultForm.note}
  const row=editing.value
  await command(row?`wastewater-update-${row.id}`:'wastewater-result',row?`/wastewater/results/${row.id}/update`:'/wastewater/results',row?{version:row.version,fields}:{...fields,sample_id:resultForm.sample_id});check()
  clearResult();await refreshSaved('results','检测结果已保存，复核后才纳入趋势')
})}
function review(action:'CONFIRM'|'RETURN'){const row=reviewing.value;if(!row)return;void run(async check=>{await command(`wastewater-review-${row.id}`,`/wastewater/results/${row.id}/review`,{version:row.version,action,note:reviewNote.value});check();reviewing.value=null;reviewNote.value='';await refreshSaved('results',action==='CONFIRM'?'结果已复核':'结果已退回，录入人可修订')})}
function showHistory(row:LabResult){void run(async check=>{const response=await queries.latest<{items:Event[]}>('history',`/wastewater/results/${row.id}/events`);check();history.value=response.items;historyTitle.value=`${row.sample_code} · ${row.analyte}`})}
const today=new Date(), chinaDate=(value:Date)=>new Date(value.getTime()+8*3600000).toISOString().slice(0,10)
const trendForm=reactive({site_id:'',analyte:'',laboratory:'',analysis_method:'',sampling_method:'COMPOSITE',start_date:chinaDate(new Date(today.getTime()-30*86400000)),end_date:chinaDate(today)})
const trendPage=ref(1)
const trendRows=computed(()=>trend.value?.points.slice((trendPage.value-1)*20,trendPage.value*20)||[])
const trend=ref<TrendResult|null>(null), appliedTrend=ref({...trendForm})
function loadTrend(){const filters={...trendForm};void run(async check=>{const response=await queries.latest<TrendResult>('trend','/wastewater/trends/search',{method:'POST',body:JSON.stringify(filters)});check();trend.value=response;trendPage.value=1;appliedTrend.value=filters})}
const plot=computed(()=>{
  const points=trend.value?.points||[], numeric=points.filter(p=>p.concentration!==null)
  const maximum=Math.max(1,...numeric.map(p=>Number(p.concentration))),min=Date.parse(`${appliedTrend.value.start_date}T00:00:00+08:00`),span=Date.parse(`${appliedTrend.value.end_date}T00:00:00+08:00`)+86400000-min
  const groups:string[]=[];let group:string[]=[]
  for(const point of points){if(point.concentration===null){if(group.length)groups.push(group.join(' '));group=[]}else group.push(`${60+(Date.parse(point.sampled_at)-min)/span*800},${220-Number(point.concentration)/maximum*180}`)}
  if(group.length)groups.push(group.join(' '))
  return {maximum,groups,dots:numeric.map(p=>({id:p.result_id,x:60+(Date.parse(p.sampled_at)-min)/span*800,y:220-Number(p.concentration)/maximum*180,label:`${p.sample_code}：${p.concentration} ng/L`}))}
})
onMounted(()=>{const focus=takeWorkbenchFocus('wastewater');if(focus){tab.value='results';keyword.value=focus.keyword||''}if(quickCreate.value==='sample'){quickCreate.value='';tab.value='samples';editor.value='samples'}void run(async()=>{await Promise.all([load(tab.value as Area,1,keyword.value),choices()])})})
</script>

<template>

  <div class="list-toolbar"><div class="wastewater-tabs" role="tablist" aria-label="污水监测业务"><button v-for="item in ([['sites','采样点'],['samples','采样记录'],['results','检测结果'],['trends','趋势研判']] as const)" :key="item[0]" role="tab" :aria-selected="tab===item[0]" :class="{secondary:tab!==item[0]}" :disabled="busy" @click="changeTab(item[0])">{{item[1]}}</button></div><button v-if="can('wastewater.write')&&tab==='sites'" type="button" :disabled="busy" @click="error='';editor='sites'">新增采样点</button><button v-else-if="can('wastewater.write')&&tab==='samples'" type="button" :disabled="busy" @click="error='';editor='samples'">登记采样</button><button v-else-if="can('wastewater.write')&&tab==='results'" type="button" :disabled="busy" @click="error='';editor='results';clearResult()">录入检测结果</button></div>
  <p v-if="error" class="error" role="alert">{{error}}</p><p v-if="notice" class="success" role="status">{{notice}}</p><p v-if="busy" class="muted" role="status">正在处理…</p>
  <div v-if="tab==='sites'" class="page-list">
    <section class="card"><form class="list-filters" @submit.prevent="run(()=>load(tab as Area,1,keyword.trim()))"><label class="list-filter-keyword">查找记录<input v-model="keyword" maxlength="100" placeholder="编号、名称或区域"></label><button :disabled="busy">查询</button></form><div class="table-wrap"><table class="table-nowrap" aria-label="污水采样点台账"><thead><tr><th scope="col" class="row-number">序号</th><th>点位编号</th><th>点位名称</th><th>所属区域</th><th>污水处理厂</th><th>汇水范围</th><th>状态</th><th>状态说明</th><th>操作</th></tr></thead><tbody><tr v-for="(row, rowIndex) in sites" :key="row.id"><td class="row-number">{{(page.sites.page-1)*20+rowIndex+1}}</td><td>{{row.code}}</td><td>{{row.name}}</td><td>{{row.district}}</td><td>{{row.plant_name||'—'}}</td><td>{{row.catchment||'—'}}</td><td>{{row.active?'启用':'停用'}}</td><td>{{row.state_note||'—'}}</td><td><button v-if="can('geography.read')" class="link" @click="openMap('WASTEWATER',row.id)">地图定位</button><button class="link" :disabled="busy||!row.active" @click="chooseSite(row)">登记采样</button><button class="link" :disabled="busy" @click="chooseTrendSite(row)">查看趋势</button><button class="link" :disabled="busy" @click="stateSite=row;stateReason=''">{{row.active?'停用':'启用'}}</button></td></tr></tbody></table><p v-if="!sites.length" class="empty">暂无采样点</p></div><Pagination :page="page.sites.page" :total="page.sites.total" :loading="busy" @change="run(()=>load('sites',$event))" /></section>
    <FormDialog v-if="editor==='sites'" title="新增采样点" :busy="busy" :error="error" @close="editor=''"><form v-if="can('wastewater.write')" @submit.prevent="addSite"><label>点位编号<input v-model="siteForm.code" maxlength="80" required></label><label>点位名称<input v-model="siteForm.name" maxlength="200" required></label><label>所属区域<input v-model="siteForm.district" maxlength="200" required></label><label>污水处理厂<input v-model="siteForm.plant_name" maxlength="200"></label><label>汇水范围说明<textarea v-model="siteForm.catchment" maxlength="1000"></textarea></label><button :disabled="busy">保存采样点</button></form></FormDialog><FormDialog v-if="stateSite" :title="stateSite.name+' · '+(stateSite.active?'停用':'启用')" :busy="busy" :error="error" @close="stateSite=null"><form class="detail" @submit.prevent="setState"><label>状态变更原因<input v-model="stateReason" maxlength="1000" required></label><button :disabled="busy">确认变更</button></form></FormDialog>
  </div>
  <div v-else-if="tab==='samples'" class="page-list">
    <section class="card"><form class="list-filters" @submit.prevent="run(()=>load(tab as Area,1,keyword.trim()))"><label class="list-filter-keyword">查找记录<input v-model="keyword" maxlength="100" placeholder="样本编号"></label><button :disabled="busy">查询</button></form><div class="table-wrap"><table class="table-nowrap" aria-label="污水采样记录"><thead><tr><th scope="col" class="row-number">序号</th><th>样本编号</th><th>采样点</th><th>采样时间</th><th>采样方式</th><th>采样人</th><th>日流量（m³/日）</th><th>质量</th><th>采样 / 质量说明</th><th>操作</th></tr></thead><tbody><tr v-for="(row, rowIndex) in samples" :key="row.id"><td class="row-number">{{(page.samples.page-1)*20+rowIndex+1}}</td><td>{{row.code}}</td><td>{{row.site_name}}</td><td>{{formatTimestamp(row.sampled_at)}}</td><td>{{methodNames[row.sampling_method]}}</td><td>{{row.collector}}</td><td>{{row.flow_m3_day??'未提供'}}</td><td>{{row.quality==='VALID'?'正常':'存疑'}}</td><td>{{row.note||'—'}}</td><td><button class="link" :disabled="busy" @click="chooseSample(row)">录入结果</button></td></tr></tbody></table><p v-if="!samples.length" class="empty">暂无采样记录</p></div><Pagination :page="page.samples.page" :total="page.samples.total" :loading="busy" @change="run(()=>load('samples',$event))" /></section>
    <FormDialog v-if="editor==='samples'" title="登记采样" :busy="busy" :error="error" @close="editor=''"><p class="muted">可在采样点台账中查找并选择点位。时间按北京时间保存；历史样本保留。</p><form v-if="can('wastewater.write')" @submit.prevent="addSample"><label>采样点<select v-model="sampleForm.site_id" required><option value="" disabled>选择点位</option><option v-for="row in selectableSites" :key="row.id" :value="row.id" :disabled="!row.active">{{row.code}} · {{row.name}}{{row.active?'':'（停用）'}}</option></select></label><label>样本编号<input v-model="sampleForm.code" maxlength="80" required></label><label>采样时间（北京时间）<input v-model="sampleForm.sampled_at" type="datetime-local" required></label><label>采样方式<select v-model="sampleForm.sampling_method"><option value="COMPOSITE">混合采样</option><option value="GRAB">瞬时采样</option></select></label><label>采样人<input v-model="sampleForm.collector" maxlength="100" required></label><label>日流量（m³/日，可空）<input v-model="sampleForm.flow_m3_day" type="number" min="0.000001" step="0.000001"></label><label>样本质量<select v-model="sampleForm.quality"><option value="VALID">正常</option><option value="FLAGGED">存疑（不纳入趋势）</option></select></label><label>采样 / 质量说明<textarea v-model="sampleForm.note" maxlength="1000" :required="sampleForm.quality==='FLAGGED'"></textarea></label><button :disabled="busy">保存采样记录</button></form></FormDialog>
  </div>
  <div v-else-if="tab==='results'" class="page-list">
    <section class="card"><form class="list-filters" @submit.prevent="run(()=>load(tab as Area,1,keyword.trim()))"><label class="list-filter-keyword">查找记录<input v-model="keyword" maxlength="100" placeholder="样本编号、指标或报告编号"></label><button :disabled="busy">查询</button></form><p class="muted">统一浓度单位 ng/L。录入人与复核人分离，已复核记录不可直接修改。</p><div class="table-wrap"><table class="table-nowrap" aria-label="污水检测结果"><thead><tr><th scope="col" class="row-number">序号</th><th>样本编号</th><th>采样点</th><th>检测指标</th><th>检出情况</th><th>浓度（ng/L）</th><th>定量限（ng/L）</th><th>实验室</th><th>检测方法</th><th>报告编号</th><th>状态</th><th>录入人</th><th>复核说明</th><th>操作</th></tr></thead><tbody><tr v-for="(row, rowIndex) in results" :key="row.id"><td class="row-number">{{(page.results.page-1)*20+rowIndex+1}}</td><td>{{row.sample_code}}</td><td>{{row.site_name}}</td><td>{{row.analyte}}</td><td>{{detectionNames[row.detection]}}</td><td>{{row.concentration??'—'}}</td><td>{{row.quantification_limit??'—'}}</td><td>{{row.laboratory}}</td><td>{{row.analysis_method}}</td><td>{{row.report_number}}</td><td>{{stateNames[row.state]}}</td><td>{{row.author}}</td><td>{{row.review_note||'—'}}</td><td><button v-if="row.created_by===currentUserId&&row.state!=='REVIEWED'" class="link" :disabled="busy" @click="editResult(row)">修改</button><button v-if="row.state==='DRAFT'&&row.created_by!==currentUserId" class="link" :disabled="busy" @click="reviewing=row;reviewNote=''">复核</button><button class="link" :disabled="busy" @click="showHistory(row)">历史</button></td></tr></tbody></table><p v-if="!results.length" class="empty">暂无检测结果</p></div><Pagination :page="page.results.page" :total="page.results.total" :loading="busy" @change="run(()=>load('results',$event))" /><form v-if="reviewing" class="detail" @submit.prevent="review('CONFIRM')"><h3>复核 {{reviewing.sample_code}} · {{reviewing.analyte}}</h3><label>复核说明<textarea v-model="reviewNote" maxlength="1000" required></textarea></label><button :disabled="busy">确认复核</button> <button type="button" class="secondary" :disabled="busy||!reviewNote.trim()" @click="review('RETURN')">退回修订</button> <button type="button" class="secondary" @click="reviewing=null">取消</button></form><section v-if="historyTitle" class="detail"><h3>{{historyTitle}} · 最近20次记录</h3><ul><li v-for="event in history" :key="event.id">{{formatTimestamp(event.created_at)}} · {{event.actor}} · {{actionNames[event.action]}} · {{event.note}} · {{event.snapshot.detection==='QUANTIFIED'?event.snapshot.concentration+' ng/L':detectionNames[event.snapshot.detection]}}</li></ul></section></section>
    <FormDialog v-if="editor==='results'" :title="editing?'修订检测结果':'录入检测结果'" :busy="busy" :error="error" @close="editor='';clearResult()"><p class="muted">可在采样记录中查找并选择样本；按原报告填写指标和方法。</p><form v-if="can('wastewater.write')" @submit.prevent="saveResult"><label>检测样本<select v-model="resultForm.sample_id" required :disabled="!!editing"><option value="" disabled>选择样本</option><option v-for="row in selectableSamples" :key="row.id" :value="row.id">{{row.code}}</option></select></label><label>检测指标<input v-model="resultForm.analyte" maxlength="120" required></label><label>检出情况<select v-model="resultForm.detection"><option value="QUANTIFIED">定量检出</option><option value="BELOW_LOQ">低于定量限</option><option value="NOT_DETECTED">未检出</option></select></label><label v-if="resultForm.detection==='QUANTIFIED'">检测浓度（ng/L）<input v-model="resultForm.concentration" type="number" min="0.000001" step="0.000001" required></label><label>定量限（ng/L）<input v-model="resultForm.quantification_limit" type="number" min="0.000001" step="0.000001" :required="resultForm.detection==='BELOW_LOQ'"></label><label>检测实验室<input v-model="resultForm.laboratory" maxlength="200" required></label><label>检测方法<input v-model="resultForm.analysis_method" maxlength="200" required></label><label>报告编号 / 版本<input v-model="resultForm.report_number" maxlength="100" required></label><label>结果说明<textarea v-model="resultForm.note" maxlength="1000"></textarea></label><button :disabled="busy">保存检测结果</button></form></FormDialog>
  </div>
  <section v-else class="card"><h2>同口径浓度趋势</h2><p class="muted">选择同一点位、指标、实验室、检测方法和采样方式，仅使用已复核且质量正常的数据。未检出与低于定量限保留原状态，不作为零值。</p><form class="list-filters wastewater-trend-filters" @submit.prevent="loadTrend"><label>趋势点位<select v-model="trendForm.site_id" required><option value="" disabled>选择点位</option><option v-for="row in selectableSites" :key="row.id" :value="row.id">{{row.code}} · {{row.name}}</option></select></label><label>趋势指标<input v-model="trendForm.analyte" maxlength="120" required></label><label>趋势实验室<input v-model="trendForm.laboratory" maxlength="200" required></label><label>趋势检测方法<input v-model="trendForm.analysis_method" maxlength="200" required></label><label>趋势采样方式<select v-model="trendForm.sampling_method"><option value="COMPOSITE">混合采样</option><option value="GRAB">瞬时采样</option></select></label><label>开始日期<input v-model="trendForm.start_date" type="date" required></label><label>结束日期<input v-model="trendForm.end_date" type="date" required></label><button :disabled="busy">查看趋势</button></form><template v-if="trend"><p role="status">{{trend.site_name}} · {{trend.sample_count}} 个样本 · {{trend.quantified_count}} 个定量结果</p><p class="muted">已应用：{{appliedTrend.analyte}} · {{appliedTrend.laboratory}} · {{appliedTrend.analysis_method}} · {{methodNames[appliedTrend.sampling_method]}} · {{appliedTrend.start_date}} 至 {{appliedTrend.end_date}}</p><p class="muted">{{trend.basis}}</p><div v-if="trend.quantified_count" class="wastewater-chart"><svg viewBox="0 0 920 270" role="img" aria-label="污水检测浓度趋势图，详细数值见下表"><path d="M60 30V220H880" fill="none" stroke="#8a9aaa"/><text x="60" y="20">浓度（ng/L）</text><text x="8" y="44">{{plot.maximum}}</text><text x="32" y="224">0</text><polyline v-for="(line,index) in plot.groups" :key="index" :points="line" fill="none" stroke="#0e7770" stroke-width="2"/><circle v-for="dot in plot.dots" :key="dot.id" :cx="dot.x" :cy="dot.y" r="4" fill="#0e7770"><title>{{dot.label}}</title></circle><text x="60" y="250">{{appliedTrend.start_date}}</text><text x="790" y="250">{{appliedTrend.end_date}}</text></svg></div><p v-else class="empty">没有可绘图的定量结果</p><div class="table-wrap"><table class="table-nowrap" aria-label="污水趋势数据"><thead><tr><th scope="col" class="row-number">序号</th><th>样本编号</th><th>采样时间</th><th>检出情况</th><th>浓度（ng/L）</th><th>定量限（ng/L）</th></tr></thead><tbody><tr v-for="(point, rowIndex) in trendRows" :key="point.result_id"><td class="row-number">{{(trendPage-1)*20+rowIndex+1}}</td><td>{{point.sample_code}}</td><td>{{formatTimestamp(point.sampled_at)}}</td><td>{{detectionNames[point.detection]}}</td><td>{{point.concentration??'—'}}</td><td>{{point.quantification_limit??'—'}}</td></tr></tbody></table></div><Pagination :page="trendPage" :total="trend.points.length" :loading="busy" label="趋势数据分页" @change="trendPage=$event" /></template><p v-else class="empty">请选择口径查询趋势</p></section>
</template>
