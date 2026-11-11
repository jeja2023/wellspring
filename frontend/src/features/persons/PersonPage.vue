<script setup lang="ts">
import Pagination from '../../shared/components/Pagination.vue'
import FormDialog from '../../shared/components/FormDialog.vue'

const {can}=useWorkspace()
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
const {error}=useWorkspace()
const creating=ref(false)
async function submitCreate(){if(await create())creating.value=false}
</script>
<template>

  <div class="page-list"><section class="card"><div class="page-toolbar page-toolbar-actions"><button v-if="can('persons.write')" type="button" :disabled="loading" @click="error='';creating=true">新建人员</button></div><form @submit.prevent="search"><label>名称或来源<input v-model="searchInput" maxlength="100" placeholder="输入名称或来源"></label><div class="actions"><button :disabled="loading">查询</button><button type="button" class="secondary" :disabled="loading" @click="clearSearch">重置</button></div></form><p class="muted">仅在当前组织范围内筛选。</p><div class="table-wrap"><table><thead><tr><th scope="col" class="row-number">序号</th><th>名称</th><th>来源</th><th>核验状态</th><th>操作</th></tr></thead><tbody><tr v-for="(person, rowIndex) in people" :key="person.id"><td class="row-number">{{(page-1)*20+rowIndex+1}}</td><td>{{person.name}}</td><td>{{person.source}}</td><td>{{person.verification_status==='UNVERIFIED' ? '未核验' : '未知状态'}}</td><td><button class="link" :disabled="loading" v-if="can('cases.read')" @click="selected=person">候选案件</button></td></tr></tbody></table><p v-if="!people.length" class="empty">{{appliedSearch ? '没有符合条件的人员草稿' : '暂无人员草稿'}}</p></div><Pagination :page="page" :total="total" :loading="loading" @change="move($event-page)" /><PersonCaseCandidates v-if="selected" :key="selected.id" :person="selected" @close="selected=null" @updated="updatePersonVersion" /></section>
  <FormDialog v-if="creating" title="新建人员草稿" :busy="loading" :error="error" @close="creating=false"><form v-if="can('persons.write')" @submit.prevent="submitCreate"><label>名称<input v-model="name" required maxlength="120" placeholder="请输入名称"></label><label>来源<input v-model="source" required maxlength="200" placeholder="请输入来源"></label><button :disabled="loading">创建草稿</button></form></FormDialog></div>
</template>
