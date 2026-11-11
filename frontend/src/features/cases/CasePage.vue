<script setup lang="ts">
import Pagination from '../../shared/components/Pagination.vue'
import FormDialog from '../../shared/components/FormDialog.vue'

import { onMounted, ref } from 'vue'
import { useWorkspace } from '../../app/workspace'
import CaseRelations from './CaseRelations.vue'
import CaseSources from './CaseSources.vue'
import ImportPage from '../imports/ImportPage.vue'
const importing=ref(false)
const selectedCase=ref<{id:string;number:string;title:string} | null>(null)
const sourceCase=ref<{id:string;number:string;title:string} | null>(null)
const { can, refreshCases, searchCases, search, loading, filteredCases, casePage, caseTotal, moveCase, makeCase, caseNumber, caseTitle } = useWorkspace()
onMounted(() => { void refreshCases() })
const {error}=useWorkspace()
const creating=ref(false)
async function submitCreate(){if(await makeCase())creating.value=false}
</script>

<template>
<div class="actions"><button v-if="can('cases.write')" type="button" :disabled="loading" @click="importing=false;error='';creating=true">新建案件</button><button type="button" class="secondary" @click="importing=false;refreshCases()">案件列表</button><button v-if="can('cases.import')" type="button" class="secondary" @click="importing=true">批量导入 / 导入记录</button></div><ImportPage v-if="importing" /><div v-else class="page-list"><section class="card"><h2>案件列表</h2><form @submit.prevent="searchCases"><label>筛选案件<input v-model="search" maxlength="100" placeholder="输入编号或名称"></label><button :disabled="loading">查询</button></form><div class="table-wrap"><table><thead><tr><th scope="col" class="row-number">序号</th><th>案件编号</th><th>案件名称</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="(c, rowIndex) in filteredCases" :key="c.id"><td class="row-number">{{(casePage-1)*20+rowIndex+1}}</td><td>{{c.number}}</td><td>{{c.title}}</td><td><span class="tag">草稿</span></td><td><button class="link" :disabled="loading" @click="selectedCase=c;sourceCase=null">案件关系</button><button class="link" :disabled="loading" v-if="can('intake.read')" @click="sourceCase=c;selectedCase=null">接警来源</button></td></tr></tbody></table><p v-if="!filteredCases.length" class="empty">暂无匹配案件</p></div><Pagination :page="casePage" :total="caseTotal" :loading="loading" @change="moveCase($event-casePage)" /><CaseSources v-if="sourceCase" :key="sourceCase.id" :source-case="sourceCase" @close="sourceCase=null" /><CaseRelations v-if="selectedCase" :key="selectedCase.id" :source-case="selectedCase" @close="selectedCase=null" /></section><FormDialog v-if="creating" title="新建案件草稿" :busy="loading" :error="error" @close="creating=false"><form @submit.prevent="submitCreate"><label>案件编号<input v-model="caseNumber" required maxlength="80"></label><label>案件名称<input v-model="caseTitle" required maxlength="200"></label><button :disabled="loading">创建草稿</button></form></FormDialog></div>
</template>
