<script setup lang="ts">
import {onBeforeUnmount,onMounted} from 'vue'
import Pagination from '../../shared/components/Pagination.vue'
import {useWorkspace} from '../../app/workspace'
import {createWorkbench,kindNames,moduleNames,queueNames,stateName,type WorkQueue} from './workbench'
import './workbench.css'
const {api,can,page,openWorkbenchTask}=useWorkspace()
const work=createWorkbench(api),{data,loading,error,load}=work
const queues=['todo','review','overdue','due_today'] as WorkQueue[]
const scopeNames={mine:'我承办',unit:'本单位可办理',claim:'本单位待接收'}
onMounted(()=>{void load(1)});onBeforeUnmount(work.dispose)
</script>
<template>
  <div class="workbench-page">
    <section class="card workbench-intro"><div><strong>今日办理</strong><p class="muted">{{data?data.today+' · ':''}}处理待办、核验资料，跟进到期事项</p></div><div class="workbench-actions"><button class="secondary" :disabled="loading" @click="load()">{{loading?'正在刷新…':'刷新事项'}}</button><button v-if="can('dashboard.read')" class="secondary" @click="page='数据大屏'">查看业务统计</button></div></section>
    <p v-if="error" class="error" role="alert">{{error}}<span v-if="data"> 当前保留上次成功查询的结果。</span><button class="link" :disabled="loading" @click="load()">重试</button></p>
    <div class="workbench-summary" role="group" aria-label="办理事项分类"><button v-for="key in queues" :key="key" type="button" class="card workbench-summary-item" :class="{'is-selected':(data?.queue||'todo')===key,'is-overdue':key==='overdue'}" :aria-pressed="(data?.queue||'todo')===key" :disabled="loading" @click="load(1,key)"><span>{{queueNames[key]}}</span><strong>{{data?data.counts[key]:'—'}}</strong><small>{{key==='todo'?'我承办及本单位可办理':key==='review'?'依现有权限独立核验':key==='overdue'?'未完成且已超过办理期限':'今天到期，优先核对'}}</small></button></div>
    <section class="card workbench-tasks">
      <div class="page-toolbar"><h2>{{queueNames[data?.queue||'todo']}}事项</h2><label>业务模块<select :value="data?.module||'all'" :disabled="loading" @change="load(1,data?.queue||'todo',($event.target as HTMLSelectElement).value)"><option value="all">全部可办理模块</option><option v-for="item in data?.available_modules||[]" :key="item.key" :value="item.key">{{item.name}}</option></select></label></div>
      <p v-if="loading&&!data" role="status" class="muted">正在读取办理事项…</p>
      <div class="table-wrap workbench-table-scroll" role="region" aria-label="办理事项表格" tabindex="0"><table class="workbench-table table-nowrap" aria-label="工作台办理事项"><thead><tr><th scope="col" class="row-number">序号</th><th scope="col">事项名称</th><th scope="col">事项类型</th><th scope="col">业务模块</th><th scope="col">办理范围</th><th scope="col">当前状态</th><th scope="col">办理期限</th><th scope="col">提醒</th><th scope="col">操作</th></tr></thead><tbody><tr v-for="(item,index) in data?.items||[]" :key="item.kind+item.id"><td class="row-number">{{((data?.page||1)-1)*10+index+1}}</td><td class="workbench-subject">{{item.title}}</td><td>{{kindNames[item.kind]}}</td><td>{{moduleNames[item.module]}}</td><td>{{scopeNames[item.scope]}}</td><td>{{stateName(item)}}</td><td>{{item.due_date||'未设置'}}</td><td><span v-if="item.overdue_days" class="workbench-deadline overdue">逾期 {{item.overdue_days}} 天</span><span v-else-if="item.due_today" class="workbench-deadline today">今日到期</span><span v-else class="muted">{{item.due_date?'未到期':'—'}}</span></td><td><button type="button" class="link" :disabled="loading" @click="openWorkbenchTask(item)">查看办理</button></td></tr></tbody></table><p v-if="data&&!data.items.length&&!loading" class="empty">{{data.available_modules.length?'暂无'+queueNames[data.queue]+'事项':'当前账号暂无可办理事项，可从左侧菜单查询获准资料'}}</p></div>
      <Pagination :page="data?.page||1" :total="data?.total||0" :page-size="10" :loading="loading" :has-more="data?.has_more||false" @change="load($event)"/>
    </section>
  </div>
</template>
