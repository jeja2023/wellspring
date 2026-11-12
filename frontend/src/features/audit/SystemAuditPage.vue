<script setup lang="ts">
import {onBeforeUnmount,onMounted} from 'vue'
import Pagination from '../../shared/components/Pagination.vue'
import {formatTimestamp} from '../../shared/time'
import {useWorkspace} from '../../app/workspace'
import {AUDIT_PAGE_SIZE,createAuditHistory} from './controller'
const {api}=useWorkspace(),history=createAuditHistory(api,'system')
const {filters,items,page,total,more,loading,error,load,search,reset}=history
onMounted(()=>load());onBeforeUnmount(history.dispose)
</script>

<template>
  <section class="card">
    <form class="list-filters" @submit.prevent="search">
      <label class="list-filter-keyword">操作账号<input v-model="filters.username" maxlength="80" placeholder="输入账号"></label>
      <label class="list-filter-keyword">操作内容<input v-model="filters.action" maxlength="80" placeholder="输入操作名称，如登录系统"></label>
      <div class="list-filter-actions"><button :disabled="loading">查询</button><button type="button" class="secondary" :disabled="loading" @click="reset">重置</button></div>
    </form>
    <p v-if="error" class="error" role="alert">{{error}} <button type="button" class="link" :disabled="loading" @click="load()">重试</button></p>
    <p v-if="loading" role="status">正在加载…</p>
    <div class="table-wrap"><table class="audit-table" aria-label="系统日志记录"><thead><tr><th scope="col" class="row-number">序号</th><th scope="col">记录时间</th><th scope="col">操作账号</th><th scope="col">组织</th><th scope="col">操作内容</th><th scope="col">对象标识</th></tr></thead>
      <tbody><tr v-for="(item,index) in items" :key="item.id"><td class="row-number">{{(page-1)*AUDIT_PAGE_SIZE+index+1}}</td><td>{{formatTimestamp(item.created_at)}}</td><td>{{item.username}}</td><td>{{item.organization}}</td><td>{{item.action_name||'其他操作'}}</td><td>{{item.object_id}}</td></tr></tbody></table><p v-if="!items.length&&!loading" class="empty">暂无符合条件的日志</p></div>
    <Pagination :page="page" :total="total" :page-size="AUDIT_PAGE_SIZE" :loading="loading" :has-more="more" @change="load($event)"/>
  </section>
</template>
