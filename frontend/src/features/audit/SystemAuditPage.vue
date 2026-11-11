<script setup lang="ts">
import Pagination from '../../shared/components/Pagination.vue'
import { formatTimestamp } from '../../shared/time'
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useWorkspace } from '../../app/workspace'
import { createLatestRequests, isCancelled } from '../../shared/api/client'

type AuditRecord = { id:string; username:string; organization:string; action:string; object_id:string; created_at:string }
type AuditPage = { items:AuditRecord[]; total:number; has_more:boolean }
const { api } = useWorkspace()
const pageRequests = createLatestRequests(api)
onBeforeUnmount(() => pageRequests.dispose())
const request = (path: string, options: RequestInit = {}) => pageRequests.latest(path.split('?')[0], path, options)
const username = ref(''), action = ref('')
const applied = ref({ username:'', action:'' })
const items = ref<AuditRecord[]>([]), page = ref(1), total = ref(0), more = ref(false), loading = ref(false), error = ref('')
async function load(next = 1) {
  loading.value = true; error.value = ''
  try {
    const response: AuditPage = await request('/admin/audit/search', { method:'POST', body:JSON.stringify({ ...applied.value, page:next, page_size:20 }) })
    items.value = response.items; total.value = response.total; more.value = response.has_more; page.value = next
  } catch (e) { if (isCancelled(e)) return;
    items.value = []; total.value = 0; more.value = false
    error.value = e instanceof Error ? e.message : '加载失败'
  } finally { loading.value = false }
}
function search() { applied.value = { username:username.value.trim(), action:action.value.trim() }; void load() }
function reset() { username.value = ''; action.value = ''; search() }
onMounted(() => load())
</script>

<template>

  <section class="card">
    <form class="case-filters" @submit.prevent="search">
      <label>操作账号<input v-model="username" maxlength="80" placeholder="输入账号"></label>
      <label>操作代码<input v-model="action" maxlength="80" placeholder="输入操作代码"></label>
      <div class="case-filter-actions"><button :disabled="loading">查询</button><button type="button" class="secondary" :disabled="loading" @click="reset">重置</button></div>
    </form>
    <p v-if="error" class="error" role="alert">{{ error }} <button class="link" @click="load(page)">重试</button></p>
    <p v-if="loading" role="status">正在加载…</p>
    <div v-else-if="!error" class="table-wrap">
      <table class="audit-table"><thead><tr><th scope="col" class="row-number">序号</th><th scope="col">时间（北京时间）</th><th scope="col">操作账号</th><th scope="col">组织</th><th scope="col">操作代码</th><th scope="col">对象标识</th></tr></thead>
      <tbody><tr v-for="(item, index) in items" :key="item.id"><td>{{ (page-1)*20+index+1 }}</td><td>{{ formatTimestamp(item.created_at) }}</td><td>{{ item.username }}</td><td>{{ item.organization }}</td><td>{{ item.action }}</td><td>{{ item.object_id }}</td></tr></tbody></table>
      <p v-if="!items.length" class="empty">暂无符合条件的日志</p>
    </div>
    <Pagination :page="page" :total="total" :loading="loading" :has-more="more" @change="load($event)" />
  </section>
</template>
