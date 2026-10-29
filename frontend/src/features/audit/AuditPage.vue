<script setup lang="ts">
import { onMounted,ref } from 'vue'
import { useWorkspace } from '../../app/workspace'
import { request } from '../../shared/api/client'
type Audit={id:string;action:string;object_id:string;created_at:string}
type Page={items:Audit[];total:number;has_more:boolean}
const {token,username,organization}=useWorkspace()
const items=ref<Audit[]>([]),page=ref(1),total=ref(0),more=ref(false),loading=ref(false),error=ref('')
async function load(next=page.value){loading.value=true;error.value='';try{const r:Page=await request(`/audit/mine?page=${next}&page_size=20`,token.value);items.value=r.items;total.value=r.total;more.value=r.has_more;page.value=next}catch(e){items.value=[];total.value=0;more.value=false;error.value=e instanceof Error?e.message:'加载失败'}finally{loading.value=false}}
onMounted(()=>load())
</script>
<template>
  <div class="title-row"><p class="eyebrow">ACCESS & AUDIT</p><h1>权限审计</h1><p class="muted">当前开发账号与个人操作记录。</p></div>
  <div class="warning">当前仅支持查看本人记录；角色、权限配置、专案授权、独立受保护审计及管理查询尚未实现。</div>
  <section class="card"><h2>当前访问范围</h2><p>账号：{{username}} · 组织：{{organization}}</p><p>开发环境按组织过滤；尚无正式岗位、字段和专案权限。</p></section>
  <section class="card intro"><h2>我的操作记录</h2><p class="muted">仅限本人在当前组织的本地审计；读取本页面本身也会产生一条审计记录。时间为 UTC。</p><p v-if="error" class="error" role="alert">{{error}} <button class="link" @click="load()">重试</button></p><p v-if="loading" role="status">正在加载…</p><div v-else class="table-wrap"><table><thead><tr><th>动作代码</th><th>对象标识</th><th>记录时间</th></tr></thead><tbody><tr v-for="item in items" :key="item.id"><td>{{item.action}}</td><td>{{item.object_id}}</td><td>{{item.created_at}}</td></tr></tbody></table><p v-if="!items.length" class="empty">暂无记录</p></div><div class="pagination"><button class="secondary" :disabled="loading || page<=1" @click="load(page-1)">上一页</button><span>第 {{page}} 页 · 查询前共 {{total}} 条</span><button class="secondary" :disabled="loading || !more" @click="load(page+1)">下一页</button></div></section>
</template>
