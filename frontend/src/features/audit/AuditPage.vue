<script setup lang="ts">
import {onBeforeUnmount,onMounted} from 'vue'
import Pagination from '../../shared/components/Pagination.vue'
import {formatTimestamp} from '../../shared/time'
import {useWorkspace} from '../../app/workspace'
import {AUDIT_PAGE_SIZE,createAuditHistory} from './controller'
const {api}=useWorkspace(),history=createAuditHistory(api,'mine')
const {filters,items,page,total,more,loading,error,load,search,reset}=history
onMounted(()=>load());onBeforeUnmount(history.dispose)
</script>

<template>
  <section class="card">
    <form class="list-filters audit-filters" @submit.prevent="search">
      <label class="list-filter-keyword">操作内容<input v-model="filters.action" maxlength="80" placeholder="输入操作名称，如创建案件"></label>
      <label class="list-filter-keyword audit-object-filter">对象标识<input v-model="filters.object_id" maxlength="36" placeholder="输入对象标识"></label>
      <label class="list-filter-select audit-date-filter">开始日期<input v-model="filters.start_date" type="date" :max="filters.end_date||undefined"></label>
      <label class="list-filter-select audit-date-filter">结束日期<input v-model="filters.end_date" type="date" :min="filters.start_date||undefined"></label>
      <div class="list-filter-actions"><button :disabled="loading">查询</button><button type="button" class="secondary" :disabled="loading" @click="reset">重置</button></div>
      <button type="button" class="secondary audit-refresh" :disabled="loading" @click="load()">刷新记录</button>
    </form>
    <p v-if="error" class="error" role="alert">{{error}} <button type="button" class="link" :disabled="loading" @click="load()">重试</button></p>
    <p v-if="loading" role="status">正在加载…</p>
    <div class="table-wrap"><table class="audit-table" aria-label="本人操作记录"><thead><tr><th scope="col" class="row-number">序号</th><th scope="col">操作内容</th><th scope="col">对象标识</th><th scope="col">记录时间</th></tr></thead>
      <tbody><tr v-for="(item,index) in items" :key="item.id"><td class="row-number">{{(page-1)*AUDIT_PAGE_SIZE+index+1}}</td><td>{{item.action_name||'其他操作'}}</td><td>{{item.object_id}}</td><td>{{formatTimestamp(item.created_at)}}</td></tr></tbody></table><p v-if="!items.length&&!loading" class="empty">暂无符合条件的记录</p></div>
    <Pagination :page="page" :total="total" :page-size="AUDIT_PAGE_SIZE" :loading="loading" :has-more="more" @change="load($event)"/>
  </section>
</template>

<style scoped>
.audit-filters .audit-object-filter{flex-basis:180px}.audit-filters .audit-date-filter{flex-basis:150px}.audit-refresh{margin-left:auto}
</style>
