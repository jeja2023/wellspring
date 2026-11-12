<script setup lang="ts">
import { createWorkspace, provideWorkspace } from './app/workspace'
import { computed,defineAsyncComponent,onMounted,ref } from 'vue'
import { pageDescriptions } from './app/pageDescriptions'
import DashboardPage from './features/dashboard/DashboardPage.vue'
import CasePage from './features/cases/CasePage.vue'
import IntakePage from './features/cases/CaseInformationPage.vue'
import PlannedPage from './features/placeholder/PlannedPage.vue'
import IntelligencePage from './features/intelligence/IntelligencePage.vue'
import WastewaterPage from './features/wastewater/WastewaterPage.vue'
import PersonPage from './features/persons/PersonPage.vue'
import SystemManagementPage from './features/system/SystemManagementPage.vue'
import PasswordDialog from './features/auth/PasswordDialog.vue'
import AuditPage from './features/audit/AuditPage.vue'
import SystemAuditPage from './features/audit/SystemAuditPage.vue'
import AiPage from './features/ai/AiPage.vue'
import DataScreenPage from './features/dashboard/DataScreenPage.vue'
import AnalysisPage from './features/analysis/AnalysisPage.vue'
import LoginPage from './features/auth/LoginPage.vue'
import logo from './assets/wellspring-mark.svg'
const GeographyPage=defineAsyncComponent(()=>import('./features/geography/GeographyPage.vue'))
const PlacesPage=defineAsyncComponent(()=>import('./features/places/PlacesPage.vue'))
const workspace = createWorkspace()
const passwordDialog=ref(false)
provideWorkspace(workspace)
const { token, username, organization, restoring, restoreError, restoreSession, page, error, notice, menuGroups, logout, roleName } = workspace
const pageDescription=computed(()=>pageDescriptions[page.value]||'')
onMounted(() => restoreSession())
</script>
<template>
  <div v-if="restoring || restoreError" class="login-wrap"><div class="login-card"><p v-if="restoring" role="status">正在恢复登录…</p><template v-else><p role="alert">{{restoreError}}</p><button type="button" @click="restoreSession">重试</button></template></div></div>
  <LoginPage v-else-if="!token" />
  <div v-else class="shell" :class="{'map-shell':page==='业务地图'}"><aside><div class="brand"><img :src="logo" alt="" class="sidebar-logo" /><span><b>清源</b><small>WELLSPRING</small></span></div><nav aria-label="主导航"><div v-for="group in menuGroups" :key="group.label" role="group" :aria-label="group.label"><div class="nav-caption">{{group.label}}</div><button v-for="item in group.items" :key="item" :class="{active:page===item}" :aria-current="page===item?'page':undefined" @click="page=item;error='';notice=''">{{item}}</button></div></nav></aside><div class="main"><header class="app-header"><div class="page-heading"><h1 class="page-title">{{page}}</h1><span v-if="pageDescription" class="page-description">{{pageDescription}}</span></div><div class="header-account"><span class="header-identity">{{organization}} · {{username}}<small v-if="roleName"> · {{roleName}}</small></span><button class="link" @click="passwordDialog=true">修改密码</button><button class="link" @click="logout">退出</button></div></header><div class="content"><p v-if="error" class="error" role="alert">{{error}}</p><p v-if="notice" class="success" role="status">{{notice}}</p>
  <DashboardPage v-if="page==='工作台'" />
  <DataScreenPage v-else-if="page==='数据大屏'" />
  <GeographyPage v-else-if="page==='业务地图'" />
  <PlacesPage v-else-if="page==='重点场所'" />
  <IntakePage v-else-if="page==='接警信息'" />
  <CasePage v-else-if="page==='案件管理'" />
  <IntelligencePage v-else-if="page==='情报线索'" />
  <WastewaterPage v-else-if="page==='污水监测'" />
  <PersonPage v-else-if="page==='人员档案'" />
  <SystemManagementPage v-else-if="['用户管理','角色管理','权限管理','组织管理'].includes(page)" :key="page" :area="({'用户管理':'users','角色管理':'roles','权限管理':'permissions','组织管理':'organizations'} as const)[page as '用户管理'|'角色管理'|'权限管理'|'组织管理']" />
  <AuditPage v-else-if="page==='操作记录'" />
  <SystemAuditPage v-else-if="page==='系统日志'" />
  <AnalysisPage v-else-if="page==='分析建模'" />
  <AiPage v-else-if="page==='智能研判'" />
  <PlannedPage v-else />
  <PasswordDialog v-if="passwordDialog" @close="passwordDialog=false" />
  </div></div></div>

</template>
