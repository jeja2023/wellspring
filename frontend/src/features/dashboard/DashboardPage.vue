<script setup lang="ts">
import { onMounted } from 'vue'
import { useWorkspace } from '../../app/workspace'
const { caseTotal, evidenceTotal, page, intelligence } = useWorkspace()
const { myTasks, myTotal, mineLoading, mineError, loadMine } = intelligence
const taskStatus: Record<string,string> = {OPEN:'待办理',RETURNED:'已退回',PENDING_REVIEW:'待复核',CLOSED:'已关闭'}
onMounted(loadMine)
</script>

<template>
<div class="title-row"><div><p class="eyebrow">OVERVIEW</p><h1>业务工作台</h1><p class="muted">查看当前组织的开发验证数据与功能进度。</p></div></div><div class="metrics"><div class="card"><span>案件草稿</span><strong>{{caseTotal}}</strong><small>当前查询结果总数</small></div><div class="card"><span>证物对象</span><strong>{{evidenceTotal}}</strong><small>含分样的授权范围总数</small></div><div class="card"><span>当前数据范围</span><strong class="metric-text">本组织</strong><small>开发环境简单组织隔离</small></div></div><section class="card intro"><h2>我的核查工单</h2><p class="muted">当前登录人承办且未关闭的工单，按办理期限排序；最多显示 5 条，打开情报线索可查看全部。</p><p v-if="mineLoading" role="status">正在加载待办…</p><p v-else-if="mineError" class="error" role="alert">{{mineError}} <button class="link" @click="loadMine">重试</button></p><p v-else-if="!myTasks.length" class="empty">暂无待办</p><div v-else class="table-wrap"><table><thead><tr><th>线索</th><th>工单状态</th><th>办理期限</th></tr></thead><tbody><tr v-for="task in myTasks" :key="task.id"><td>{{task.clue_title}}</td><td>{{taskStatus[task.status] || '未知状态'}}</td><td>{{task.due_date || '未设置'}}</td></tr></tbody></table><p class="muted">共 {{myTotal}} 条；列表仅含当前组织且当前账号承办的工单。</p></div><button class="secondary" @click="page='情报线索'">进入情报线索</button></section><div class="card intro"><h2>开始使用</h2><p>先创建案件草稿，再登记证物和初始重量；可在证物管理中查看流水或进行分样。</p><div class="actions"><button @click="page='案件管理'">进入案件管理</button><button class="secondary" @click="page='证物管理'">进入证物管理</button></div><p class="muted">人员、导入、审批、审计中心及 AI 等功能仍待建设。</p></div>
</template>
