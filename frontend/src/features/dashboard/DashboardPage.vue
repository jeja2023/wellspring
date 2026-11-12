<script setup lang="ts">
import {computed,onBeforeUnmount,onMounted} from 'vue'
import Pagination from '../../shared/components/Pagination.vue'
import {formatTimestamp} from '../../shared/time'
import {useWorkspace} from '../../app/workspace'
import {createWorkbench,kindNames,moduleNames,queueNames,stateName,type WorkQueue} from './workbench'
import './workbench.css'
const {api,can,page,openWorkbenchTask,startWork}=useWorkspace()
const work=createWorkbench(api),{data,loading,error,load}=work
const queues=['todo','review','overdue','due_today'] as WorkQueue[]
const shortcuts=computed(()=>[
  {action:'case',name:'登记案件',description:'登记案件并关联来源',permissions:['cases.read','cases.write']},
  {action:'clue',name:'录入线索',description:'登记来源和待核验内容',permissions:['intelligence.read','intelligence.write']},
  {action:'person',name:'新建人员档案',description:'建立档案并核对身份',permissions:['persons.read','persons.write']},
  {action:'place',name:'新增场所',description:'登记场所与管理依据',permissions:['places.read','places.write']},
  {action:'sample',name:'登记采样',description:'选择点位并保存采样记录',permissions:['wastewater.read','wastewater.write']},
].filter(item=>item.permissions.every(can)))
const scopeNames={mine:'我承办',unit:'本单位可办理',claim:'本单位待接收'}
onMounted(()=>{void load(1)});onBeforeUnmount(work.dispose)
</script>
<template>
  <div class="workbench-page">
    <section class="card workbench-intro"><div><strong>今日办理</strong><p class="muted">{{data?data.today+' · ':''}}处理待办、核验资料，跟进到期事项</p></div><div class="workbench-actions"><button class="secondary" :disabled="loading" @click="load()">{{loading?'正在刷新…':'刷新事项'}}</button><button v-if="can('dashboard.read')" class="secondary" @click="page='数据大屏'">查看业务统计</button></div></section>
    <p v-if="error" class="error" role="alert">{{error}}<span v-if="data"> 当前保留上次成功查询的结果。</span><button class="link" :disabled="loading" @click="load()">重试</button></p>
    <div class="workbench-summary" role="group" aria-label="办理事项分类"><button v-for="key in queues" :key="key" type="button" class="card workbench-summary-item" :class="{'is-selected':(data?.queue||'todo')===key,'is-overdue':key==='overdue'}" :aria-pressed="(data?.queue||'todo')===key" :disabled="loading" @click="load(1,key)"><span>{{queueNames[key]}}</span><strong>{{data?data.counts[key]:'—'}}</strong><small>{{key==='todo'?'我承办及本单位可办理':key==='review'?'依现有权限独立核验':key==='overdue'?'未完成且已超过办理期限':'今天到期，优先核对'}}</small></button></div>
    <section class="card workbench-tasks">
      <div class="page-toolbar"><div><h2>{{queueNames[data?.queue||'todo']}}事项</h2><p class="muted workbench-caption">按办理期限排序；逾期与到期按北京时间计算</p></div><label>业务模块<select :value="data?.module||'all'" :disabled="loading" @change="load(1,data?.queue||'todo',($event.target as HTMLSelectElement).value)"><option value="all">全部可办理模块</option><option v-for="item in data?.available_modules||[]" :key="item.key" :value="item.key">{{item.name}}</option></select></label></div>
      <p v-if="loading&&!data" role="status" class="muted">正在读取办理事项…</p>
      <div class="table-wrap"><table class="workbench-table" aria-label="工作台办理事项"><thead><tr><th scope="col" class="row-number">序号</th><th scope="col">事项</th><th scope="col">业务模块</th><th scope="col">办理范围</th><th scope="col">当前状态</th><th scope="col">办理期限</th><th scope="col">提醒</th><th scope="col">操作</th></tr></thead><tbody><tr v-for="(item,index) in data?.items||[]" :key="item.kind+item.id"><td class="row-number">{{((data?.page||1)-1)*10+index+1}}</td><td class="workbench-subject"><strong>{{item.title}}</strong><small>{{kindNames[item.kind]}}</small></td><td>{{moduleNames[item.module]}}</td><td>{{scopeNames[item.scope]}}</td><td>{{stateName(item)}}</td><td>{{item.due_date||'未设置'}}</td><td><span v-if="item.overdue_days" class="workbench-deadline overdue">逾期 {{item.overdue_days}} 天</span><span v-else-if="item.due_today" class="workbench-deadline today">今日到期</span><span v-else class="muted">{{item.due_date?'未到期':'—'}}</span></td><td><button type="button" class="link" :disabled="loading" @click="openWorkbenchTask(item)">查看办理</button></td></tr></tbody></table><p v-if="data&&!data.items.length&&!loading" class="empty">{{data.available_modules.length?'暂无'+queueNames[data.queue]+'事项':'当前账号暂无可办理事项，可从左侧菜单查询获准资料'}}</p></div>
      <Pagination :page="data?.page||1" :total="data?.total||0" :page-size="10" :loading="loading" :has-more="data?.has_more||false" @change="load($event)"/>
      <p v-if="data" class="muted workbench-updated">更新于 {{formatTimestamp(data.generated_at)}} · “本单位可办理”为共享事项，领取或办理前仍按业务规则校验。</p>
    </section>
    <section v-if="shortcuts.length" class="card workbench-shortcuts"><h2>快捷办理</h2><div class="workbench-shortcut-list"><button v-for="item in shortcuts" :key="item.action" class="secondary" @click="startWork(item.action)"><strong>{{item.name}}</strong><span>{{item.description}}</span></button></div></section>
  </div>
</template>
