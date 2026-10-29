<script setup lang="ts">
import { useWorkspace } from '../../app/workspace'
const { searchCases, search, loading, filteredCases, casePage, caseTotal, moveCase, makeCase, caseNumber, caseTitle } = useWorkspace()
</script>

<template>
<div class="title-row"><div><p class="eyebrow">CASE MANAGEMENT</p><h1>案件管理</h1><p class="muted">登记本组织案件草稿，案件编号在本组织内唯一。</p></div></div><div class="two-column"><section class="card"><h2>案件列表</h2><form @submit.prevent="searchCases"><label>筛选案件<input v-model="search" placeholder="输入编号或名称"></label><button :disabled="loading">查询</button></form><div class="table-wrap"><table><thead><tr><th>案件编号</th><th>案件名称</th><th>状态</th></tr></thead><tbody><tr v-for="c in filteredCases" :key="c.id"><td>{{c.number}}</td><td>{{c.title}}</td><td><span class="tag">草稿</span></td></tr></tbody></table><p v-if="!filteredCases.length" class="empty">暂无匹配案件</p></div><div class="pagination"><button class="secondary" :disabled="loading || casePage<=1" @click="moveCase(-1)">上一页</button><span>第 {{casePage}} 页 · 共 {{caseTotal}} 条</span><button class="secondary" :disabled="loading || casePage*20>=caseTotal" @click="moveCase(1)">下一页</button></div></section><section class="card"><h2>新建案件草稿</h2><form @submit.prevent="makeCase"><label>案件编号<input v-model="caseNumber" required maxlength="80"></label><label>案件名称<input v-model="caseTitle" required maxlength="200"></label><button :disabled="loading">创建草稿</button></form></section></div>
</template>
