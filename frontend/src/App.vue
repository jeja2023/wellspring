<script setup lang="ts">
import { createWorkspace, provideWorkspace } from './app/workspace'
import DashboardPage from './features/dashboard/DashboardPage.vue'
import CasePage from './features/cases/CasePage.vue'
import EvidencePage from './features/evidence/EvidencePage.vue'
import PlannedPage from './features/placeholder/PlannedPage.vue'
import IntelligencePage from './features/intelligence/IntelligencePage.vue'
import PersonPage from './features/persons/PersonPage.vue'
import ImportPage from './features/imports/ImportPage.vue'
import AuditPage from './features/audit/AuditPage.vue'
import AiPage from './features/ai/AiPage.vue'
import LoginPage from './features/auth/LoginPage.vue'
import logo from './assets/wellspring-mark.svg'
const workspace = createWorkspace()
provideWorkspace(workspace)
const { token, username, organization, page, error, notice, menu, logout } = workspace
</script>
<template>
  <LoginPage v-if="!token" />
  <div v-else class="shell"><aside><div class="brand"><img :src="logo" alt="" class="sidebar-logo" /><span><b>清源</b><small>WELLSPRING</small></span></div><div class="nav-caption">业务导航</div><nav aria-label="主导航"><button v-for="item in menu" :key="item" :class="{active:page===item}" @click="page=item;error='';notice=''">{{item}}</button></nav><div class="side-foot">开发验证版本<br>仅限虚构数据</div></aside><div class="main"><header><div><b>{{page}}</b><span class="header-sub"> / 禁毒业务协同与智能研判平台</span></div><div>{{organization}} · {{username}} <button class="link" @click="logout">退出</button></div></header><div class="content"><div class="banner">开发验证环境：功能和权限尚未完成验收，禁止用于真实业务或生产环境。</div><p v-if="error" class="error" role="alert">{{error}}</p><p v-if="notice" class="success" role="status">{{notice}}</p>
  <DashboardPage v-if="page==='工作台'" />
  <CasePage v-else-if="page==='案件管理'" />
  <EvidencePage v-else-if="page==='证物管理'" />
  <IntelligencePage v-else-if="page==='情报线索'" />
  <PersonPage v-else-if="page==='人员档案'" />
  <ImportPage v-else-if="page==='数据导入'" />
  <AuditPage v-else-if="page==='权限审计'" />
  <AiPage v-else-if="page==='智能解析'" />
  <PlannedPage v-else />
  </div></div></div>

</template>
