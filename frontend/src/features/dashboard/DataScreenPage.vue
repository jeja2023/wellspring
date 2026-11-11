<script setup lang="ts">
import {computed,onBeforeUnmount,onMounted,ref} from 'vue'
import {useWorkspace} from '../../app/workspace'
import {createLatestRequests,isCancelled} from '../../shared/api/client'
import {formatTimestamp} from '../../shared/time'
import Pagination from '../../shared/components/Pagination.vue'
import DistributionPanel from './DistributionPanel.vue'
import {colors,linePath,type Overview} from './screen'
import './screen.css'

const {api,can,page:workspacePage}=useWorkspace(),requests=createLatestRequests(api)
const board=ref<HTMLElement|null>(null),data=ref<Overview|null>(null),days=ref<7|30|90>(30)
const loading=ref(false),error=ref(''),fullscreen=ref(false),automatic=ref(false),seriesKey=ref(''),dailyPage=ref(1),showDaily=ref(false)
let refreshTimer:ReturnType<typeof setInterval>|undefined
const series=computed(()=>data.value?.trend.series.filter(item=>!seriesKey.value||item.key===seriesKey.value)||[])
const maximum=computed(()=>Math.max(3,Math.ceil(Math.max(0,...series.value.flatMap(item=>item.values))/3)*3))
const dateTicks=computed(()=>{const dates=data.value?.trend.dates||[];return [...new Set([0,Math.floor((dates.length-1)/2),dates.length-1])].filter(i=>i>=0).map(index=>({index,label:dates[index]?.slice(5)}))})
const dailyRows=computed(()=>data.value?.trend.dates.map((date,index)=>({date,index})).slice((dailyPage.value-1)*20,dailyPage.value*20)||[])
async function load(target=days.value){loading.value=true;error.value='';try{
  const result=await requests.latest<Overview>('overview',`/dashboard/overview?days=${target}`)
  data.value=result;days.value=result.range.days;dailyPage.value=1
}catch(e){if(!isCancelled(e))error.value=e instanceof Error?e.message:'统计加载失败'}finally{loading.value=false}}
async function toggleFullscreen(){error.value='';try{
  if(document.fullscreenElement===board.value)await document.exitFullscreen()
  else if(board.value?.requestFullscreen)await board.value.requestFullscreen()
  else error.value='当前浏览器不支持全屏展示'
}catch{error.value='无法进入全屏，请检查浏览器设置'}}
function fullscreenChanged(){fullscreen.value=document.fullscreenElement===board.value}
onMounted(()=>{void load();document.addEventListener('fullscreenchange',fullscreenChanged);refreshTimer=setInterval(()=>{if(automatic.value&&!loading.value&&!document.hidden)void load()},60000)})
onBeforeUnmount(()=>{requests.dispose();clearInterval(refreshTimer);document.removeEventListener('fullscreenchange',fullscreenChanged);if(document.fullscreenElement===board.value)void document.exitFullscreen()})
</script>
<template>
  <div ref="board" class="data-screen" :class="{'is-fullscreen':fullscreen}">
    <section class="card screen-toolbar">
      <div><strong>{{data?.organization||'当前组织'}}</strong><p class="muted">{{data?'更新于 '+formatTimestamp(data.generated_at):'综合业务统计'}}</p></div>
      <div class="screen-controls"><label>新增统计周期<select :value="days" :disabled="loading" @change="load(Number(($event.target as HTMLSelectElement).value) as 7|30|90)"><option :value="7">近 7 天</option><option :value="30">近 30 天</option><option :value="90">近 90 天</option></select></label><label class="check-label"><input v-model="automatic" type="checkbox">每分钟刷新</label><button class="secondary" :disabled="loading" @click="load()">{{loading?'更新中…':'刷新数据'}}</button><button class="secondary" @click="toggleFullscreen">{{fullscreen?'退出全屏':'全屏展示'}}</button></div>
    </section>
    <p v-if="error" class="error" role="alert">{{error}} <span v-if="data">当前仍显示上次成功获取的数据。</span></p>
    <p v-if="loading&&!data" class="card muted" role="status">正在汇总授权范围内的数据…</p>
    <template v-if="data">
      <div v-if="!data.metrics.length" class="card empty">当前角色没有可统计的业务模块权限，请联系管理员。</div>
      <div class="screen-metrics"><div v-for="(metric,index) in data.metrics" :key="metric.key" class="card screen-metric" :style="{'--metric-color':colors[index%colors.length]}"><span>{{metric.label}}</span><div><strong>{{metric.total.toLocaleString('zh-CN')}}</strong><small>{{metric.unit}}</small></div><p>近 {{data.range.days}} 天新增 <b>{{metric.period_count.toLocaleString('zh-CN')}}</b></p></div></div>
      <section v-if="data.metrics.length" class="card screen-trend"><div class="page-toolbar"><h2>业务新增趋势</h2><label>查看模块<select v-model="seriesKey"><option value="">全部授权模块</option><option v-for="item in data.trend.series" :key="item.key" :value="item.key">{{item.label}}</option></select></label></div>
        <p class="muted">{{data.range.start_date}} 至 {{data.range.end_date}} · 按北京时间的记录创建日期统计</p>
        <div class="screen-chart"><svg viewBox="0 0 780 250" role="img" aria-label="各业务模块每天新增记录折线图"><title>各业务模块每天新增记录；准确数值可在下方每日数据表查看</title><g v-for="tick in [0,1,2,3]" :key="tick"><line x1="44" x2="744" :y1="210-tick*60" :y2="210-tick*60" class="screen-grid-line"/><text x="34" :y="214-tick*60" text-anchor="end">{{Math.round(maximum*tick/3)}}</text></g><path v-for="item in series" :key="item.key" :d="linePath(item.values,maximum)" fill="none" :stroke="colors[data.trend.series.findIndex(row=>row.key===item.key)%colors.length]" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/><text v-for="tick in dateTicks" :key="tick.index" :x="44+tick.index*700/Math.max(1,data.trend.dates.length-1)" y="238" text-anchor="middle">{{tick.label}}</text></svg></div>
        <div class="screen-legend"><span v-for="item in series" :key="item.key"><i :style="{background:colors[data.trend.series.findIndex(row=>row.key===item.key)%colors.length]}"></i>{{item.label}}</span><button class="link" type="button" @click="showDaily=!showDaily">{{showDaily?'收起每日数据':'查看每日数据'}}</button></div>
        <template v-if="showDaily"><div class="table-wrap"><table><thead><tr><th scope="col" class="row-number">序号</th><th scope="col">日期</th><th v-for="item in data.trend.series" :key="item.key" scope="col">{{item.label}}</th></tr></thead><tbody><tr v-for="row in dailyRows" :key="row.date"><td class="row-number">{{row.index+1}}</td><td>{{row.date}}</td><td v-for="item in data.trend.series" :key="item.key">{{item.values[row.index]}}</td></tr></tbody></table></div><Pagination :page="dailyPage" :total="data.trend.dates.length" @change="dailyPage=$event" /></template>
      </section>
      <div class="screen-distributions"><DistributionPanel v-if="data.breakdowns.intake" title="接警类型分布" :items="data.breakdowns.intake"/><DistributionPanel v-if="data.breakdowns.tasks" title="核查工单状态" :items="data.breakdowns.tasks"/><DistributionPanel v-if="data.breakdowns.models" title="业务模型状态" :items="data.breakdowns.models"/><DistributionPanel v-if="data.breakdowns.results" title="污水检测复核状态" :items="data.breakdowns.results"/><DistributionPanel v-if="data.breakdowns.sites" title="采样点运行状态" :items="data.breakdowns.sites"/></div>
      <section class="card screen-notes"><p class="muted">{{data.date_basis}} 大屏只显示当前组织及当前角色可查询的模块，不包含业务原文或个人明细。</p><button v-if="can('ai.generate')" class="secondary" @click="workspacePage='智能研判'">前往 AI 统计解读</button></section>
    </template>
  </div>
</template>
