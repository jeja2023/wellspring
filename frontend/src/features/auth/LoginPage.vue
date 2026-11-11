<script setup lang="ts">
import { useWorkspace } from '../../app/workspace'
import logo from '../../assets/wellspring-mark.svg'
import './login.css'
const { username, password, error, loading, login } = useWorkspace()
</script>

<template>
  <main class="login-page">
    <section class="login-story" aria-label="清源平台介绍">
      <div class="story-grid" aria-hidden="true"></div>
      <div class="story-brand">
        <img :src="logo" alt="" class="story-logo" />
        <div><strong>清源</strong><span>禁毒业务协同</span></div>
        <i aria-hidden="true"></i>
        <p>禁毒全流程协同平台</p>
      </div>
      <div class="story-content">
        <div class="story-kicker"><span></span> 禁毒业务协同与智能研判平台</div>
        <h1>清本溯源<br /><em>协同共治</em></h1>
        <p class="story-description">以数据为链，以协同为基，以治理为本。<br />让业务流转更清晰，让协同处置更有序。</p>
        <div class="story-divider"></div>
        <div class="story-pillars" aria-label="平台业务范围">
          <div><b>人</b><span>人员档案</span></div>
          <div><b>案</b><span>案件协同</span></div>
          <div><b>物</b><span>证物管理</span></div>
          <div><b>情</b><span>情报线索</span></div>
        </div>
      </div>
      <div class="story-art" aria-hidden="true">
        <svg viewBox="0 0 560 370" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M-35 285C91 283 118 197 218 203C318 209 332 291 444 275C498 267 525 243 594 195" stroke="#91D3C3" stroke-width="1" opacity=".32"/>
          <path d="M-25 318C92 313 135 229 226 235C315 241 342 317 450 302C511 294 536 267 596 227" stroke="#91D3C3" stroke-width="1" opacity=".18"/>
          <path d="M-5 250C99 249 120 165 224 170C326 175 339 252 442 243C499 238 531 204 590 160" stroke="#91D3C3" stroke-width="1" opacity=".18"/>
          <circle cx="220" cy="203" r="5" fill="#9EDBCB" opacity=".9"/><circle cx="220" cy="203" r="13" stroke="#9EDBCB" opacity=".3"/>
          <circle cx="443" cy="275" r="4" fill="#9EDBCB" opacity=".75"/><circle cx="443" cy="275" r="11" stroke="#9EDBCB" opacity=".25"/>
          <circle cx="92" cy="267" r="3" fill="#9EDBCB" opacity=".5"/>
          <path d="M220 90v110M213 95h14M220 90l3 3M220 90l-3 3" stroke="#91D3C3" opacity=".2"/>
        </svg>
      </div>
      <div class="story-foot"><span class="story-foot-line"></span> 清源 <span class="story-foot-sep">/</span> 以数据为链 · 以协同为基</div>
    </section>

    <section class="login-panel" aria-labelledby="login-heading">
      <div class="login-panel-top"><span class="top-dot"></span> 业务系统登录</div>
      <div class="login-form-wrap">
        <div class="mobile-brand"><img :src="logo" alt="" /><span><strong>清源</strong><small>禁毒业务协同平台</small></span></div>
        <div class="login-label">账号登录 <span></span></div>
        <h2 id="login-heading">欢迎登录清源</h2>
        <p class="login-subtitle">请输入您的账号信息，进入业务工作台。</p>
        <form @submit.prevent="login" class="login-form">
          <label for="login-username">账号</label>
          <input id="login-username" v-model="username" autocomplete="username" maxlength="80" placeholder="请输入账号" required />
          <label for="login-password">密码</label>
          <input id="login-password" v-model="password" type="password" autocomplete="current-password" maxlength="256" placeholder="请输入密码" required />
          <p v-if="error" class="login-error" role="alert">{{ error }}</p>
          <button type="submit" :disabled="loading">{{ loading ? '正在登录…' : '登录系统' }} <span aria-hidden="true">→</span></button>
        </form>
        <p class="login-help">使用经授权的账号登录。如遇登录问题，请联系系统管理员。</p>
      </div>
      <div class="login-panel-foot"><span>清源 · 禁毒全流程协同平台</span><span>协同 · 溯源 · 治理</span></div>
    </section>
  </main>
</template>
