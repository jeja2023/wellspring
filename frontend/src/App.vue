<script setup lang="ts">
import { createWorkspace, provideWorkspace } from './app/workspace'
import DashboardPage from './features/dashboard/DashboardPage.vue'
import CasePage from './features/cases/CasePage.vue'
import EvidencePage from './features/evidence/EvidencePage.vue'
import PlannedPage from './features/placeholder/PlannedPage.vue'
import IntelligencePage from './features/intelligence/IntelligencePage.vue'
const workspace = createWorkspace()
provideWorkspace(workspace)
const { token, username, password, organization, page, error, notice, loading, menu, login, logout } = workspace
</script>
<template>
  <div v-if="!token" class="login-wrap"><main class="login-card"><div class="brand-mark">源</div><p class="eyebrow">WELLSPRING</p><h1>清源</h1><p class="muted">禁毒全流程协同平台</p><div class="warning">开发验证环境 · 禁止录入真实业务数据</div><form @submit.prevent="login"><label>账号<input v-model="username" autocomplete="username" required></label><label>密码<input v-model="password" type="password" autocomplete="current-password" required></label><p v-if="error" class="error" role="alert">{{error}}</p><button :disabled="loading">登录</button></form></main></div>
  <div v-else class="shell"><aside><div class="brand"><span class="brand-mark small">源</span><span><b>清源</b><small>WELLSPRING</small></span></div><div class="nav-caption">业务导航</div><nav aria-label="主导航"><button v-for="item in menu" :key="item" :class="{active:page===item}" @click="page=item;error='';notice=''">{{item}}</button></nav><div class="side-foot">开发验证版本<br>仅限虚构数据</div></aside><div class="main"><header><div><b>{{page}}</b><span class="header-sub"> / 禁毒业务协同与智能研判平台</span></div><div>{{organization}} · {{username}} <button class="link" @click="logout">退出</button></div></header><div class="content"><div class="banner">开发验证环境：功能和权限尚未完成验收，禁止用于真实业务或生产环境。</div><p v-if="error" class="error" role="alert">{{error}}</p><p v-if="notice" class="success" role="status">{{notice}}</p>
  <DashboardPage v-if="page==='工作台'" />
  <CasePage v-else-if="page==='案件管理'" />
  <EvidencePage v-else-if="page==='证物管理'" />
  <IntelligencePage v-else-if="page==='情报线索'" />
  <PlannedPage v-else />
  </div></div></div>

</template>
