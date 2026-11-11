<script setup lang="ts">
import Pagination from '../../shared/components/Pagination.vue'
import { formatTimestamp } from '../../shared/time'
import { onBeforeUnmount, onMounted,ref } from 'vue'
import { useWorkspace } from '../../app/workspace'
import { createLatestRequests, isCancelled } from '../../shared/api/client'
type Audit={id:string;action:string;object_id:string;created_at:string}
type Page={items:Audit[];total:number;has_more:boolean}
const {api}=useWorkspace()
const pageRequests = createLatestRequests(api)
onBeforeUnmount(() => pageRequests.dispose())
const request = (path: string, options: RequestInit = {}) => pageRequests.latest(path.split('?')[0], path, options)
const items=ref<Audit[]>([]),page=ref(1),total=ref(0),more=ref(false),loading=ref(false),error=ref('')
async function load(next=page.value){loading.value=true;error.value='';try{const r:Page=await request(`/audit/mine?page=${next}&page_size=20`);items.value=r.items;total.value=r.total;more.value=r.has_more;page.value=next}catch(e){if(isCancelled(e))return;items.value=[];total.value=0;more.value=false;error.value=e instanceof Error?e.message:'加载失败'}finally{loading.value=false}}
onMounted(()=>load())
</script>
<template>


  <section class="card"><p class="muted">仅显示本人操作记录；读取本页面本身也会产生一条审计记录。时间为北京时间。</p><p v-if="error" class="error" role="alert">{{error}} <button class="link" @click="load()">重试</button></p><p v-if="loading" role="status">正在加载…</p><div v-else class="table-wrap"><table class="audit-table"><thead><tr><th scope="col" class="row-number">序号</th><th scope="col">动作代码</th><th scope="col">对象标识</th><th scope="col">记录时间</th></tr></thead><tbody><tr v-for="(item, index) in items" :key="item.id"><td class="row-number">{{(page-1)*20+index+1}}</td><td>{{item.action}}</td><td>{{item.object_id}}</td><td>{{formatTimestamp(item.created_at)}}</td></tr></tbody></table><p v-if="!items.length" class="empty">暂无记录</p></div><Pagination :page="page" :total="total" :loading="loading" :has-more="more" @change="load($event)" /></section>
</template>
