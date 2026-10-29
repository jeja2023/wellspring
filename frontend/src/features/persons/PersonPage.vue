<script setup lang="ts">
import { onMounted, ref } from 'vue'
import PersonCaseCandidates from './PersonCaseCandidates.vue'
const selected=ref<{id:string;name:string;version:number}|null>(null)
import { useWorkspace } from '../../app/workspace'
const {persons,loading}=useWorkspace()
const {people,page,total,name,source,searchInput,appliedSearch,search,clearSearch,activate,move,create}=persons
function updatePersonVersion(version:number) {
  if (!selected.value) return
  selected.value.version=version
  const row=people.value.find(person=>person.id===selected.value?.id)
  if (row) row.version=version
}
onMounted(activate)
</script>
<template>
  <div class="title-row"><div><p class="eyebrow">PERSONS</p><h1>人员档案</h1><p class="muted">最小人员草稿，仅用于虚构数据验证。</p></div></div>
  <div class="warning">当前仅保存名称与来源，不核验身份、去重或确认任何法律状态；组织内可见，不具备正式字段和岗位授权。</div>
  <div class="two-column"><section class="card"><h2>人员草稿</h2><form @submit.prevent="search"><label>名称或来源<input v-model="searchInput" maxlength="100" placeholder="输入名称或来源"></label><div class="actions"><button :disabled="loading">查询</button><button type="button" class="secondary" :disabled="loading" @click="clearSearch">重置</button></div></form><p class="muted">仅在当前组织范围内筛选。</p><div class="table-wrap"><table><thead><tr><th>名称</th><th>来源</th><th>核验状态</th><th>操作</th></tr></thead><tbody><tr v-for="person in people" :key="person.id"><td>{{person.name}}</td><td>{{person.source}}</td><td>{{person.verification_status==='UNVERIFIED' ? '未核验' : '未知状态'}}</td><td><button class="link" :disabled="loading" @click="selected=person">候选案件</button></td></tr></tbody></table><p v-if="!people.length" class="empty">{{appliedSearch ? '没有符合条件的人员草稿' : '暂无人员草稿'}}</p></div><div class="pagination"><button class="secondary" :disabled="loading || page<=1" @click="move(-1)">上一页</button><span>第 {{page}} 页 · 共 {{total}} 条</span><button class="secondary" :disabled="loading || page*20>=total" @click="move(1)">下一页</button></div><PersonCaseCandidates v-if="selected" :key="selected.id" :person="selected" @close="selected=null" @updated="updatePersonVersion" /></section>
  <section class="card"><h2>新建人员草稿</h2><form @submit.prevent="create"><label>名称<input v-model="name" required maxlength="120" placeholder="仅填写虚构名称"></label><label>来源<input v-model="source" required maxlength="200" placeholder="仅填写虚构来源"></label><button :disabled="loading">创建草稿</button></form></section></div>
</template>
