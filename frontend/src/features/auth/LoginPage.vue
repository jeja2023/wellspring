<script setup lang="ts">
import { useWorkspace } from '../../app/workspace'
import logo from '../../assets/wellspring-mark.svg'
import './login.css'
const { username, password, error, loading, login } = useWorkspace()
const appVersion = __APP_VERSION__
</script>

<template>
  <main class="login-page">
    <section class="login-story" aria-label="清源平台介绍">
      <div class="story-grid" aria-hidden="true"></div>
      <div class="story-brand">
        <img :src="logo" alt="" class="story-logo" />
        <div><strong>清源</strong><span>WELLSPRING</span></div>
      </div>
      <div class="story-content">
        <div class="story-kicker"><span></span> 禁毒智能研判与综合治理平台</div>
        <h1>清本溯源<br /><em>协同共治</em></h1>
        <p class="story-description">以数据为链，以流程为纲，以治理为本。<br />让线索流转更清晰，让联动处置更有序。</p>
        <div class="story-divider"></div>
        <div class="story-pillars" aria-label="平台业务范围">
          <div><b>人</b><span>人员档案</span></div>
          <div><b>案</b><span>案件管理</span></div>
          <div><b>模</b><span>数据建模</span></div>
          <div><b>情</b><span>情报线索</span></div>
        </div>
      </div>
      <div class="story-art" aria-hidden="true">
        <svg viewBox="0 0 800 900" fill="none" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <linearGradient id="ws-wave-grad-a" x1="0" y1="620" x2="800" y2="760" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stop-color="#2573db" stop-opacity="0.16" />
              <stop offset="55%" stop-color="#14a398" stop-opacity="0.14" />
              <stop offset="100%" stop-color="#14a398" stop-opacity="0.02" />
            </linearGradient>
            <linearGradient id="ws-wave-grad-b" x1="60" y1="700" x2="800" y2="880" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stop-color="#14a398" stop-opacity="0.06" />
              <stop offset="60%" stop-color="#2573db" stop-opacity="0.15" />
              <stop offset="100%" stop-color="#2573db" stop-opacity="0.04" />
            </linearGradient>
            <linearGradient id="ws-stroke-flow" x1="80" y1="740" x2="780" y2="540" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stop-color="#2573db" stop-opacity="0.05" />
              <stop offset="48%" stop-color="#2573db" stop-opacity="0.35" />
              <stop offset="100%" stop-color="#14a398" stop-opacity="0.4" />
            </linearGradient>
            <radialGradient id="ws-ripple-glow" cx="0.5" cy="0.5" r="0.5">
              <stop offset="0%" stop-color="#2573db" stop-opacity="0.18" />
              <stop offset="55%" stop-color="#14a398" stop-opacity="0.07" />
              <stop offset="100%" stop-color="#14a398" stop-opacity="0" />
            </radialGradient>
          </defs>

          <!-- 溯源光晕与同心涟漪 -->
          <circle cx="600" cy="600" r="290" fill="url(#ws-ripple-glow)" />
          <circle cx="600" cy="600" r="110" stroke="#2573db" stroke-opacity="0.14" stroke-width="1" />
          <circle cx="600" cy="600" r="175" stroke="#14a398" stroke-opacity="0.13" stroke-width="1" stroke-dasharray="5 6" />
          <circle cx="600" cy="600" r="245" stroke="#2573db" stroke-opacity="0.1" stroke-width="1" />
          <circle cx="600" cy="600" r="325" stroke="#14a398" stroke-opacity="0.08" stroke-width="1" />

          <!-- 清源盾形水印轮廓 -->
          <path
            d="M600 472l78 30v54c0 56-33 102-78 126-45-24-78-70-78-126v-54l78-30Z"
            fill="#2573db"
            fill-opacity="0.045"
            stroke="#2573db"
            stroke-opacity="0.14"
            stroke-width="1.2"
          />

          <!-- 流动数据丝带与渐变面 -->
          <path d="M-40 720C140 708 245 588 410 604C570 620 635 710 830 592V920H-40Z" fill="url(#ws-wave-grad-a)" />
          <path d="M-40 785C165 768 295 660 465 680C620 698 690 778 830 682V920H-40Z" fill="url(#ws-wave-grad-b)" />
          <path d="M-20 718C150 704 252 586 415 602C574 618 638 708 820 592" stroke="url(#ws-stroke-flow)" stroke-width="1.6" />
          <path d="M-20 760C168 746 285 636 452 654C610 672 675 748 825 648" stroke="#14a398" stroke-opacity="0.28" stroke-width="1.1" />
          <path d="M20 680C178 666 268 548 424 562C568 576 642 664 812 544" stroke="#2573db" stroke-opacity="0.18" stroke-width="1" />

          <!-- 协同拓扑节点连线 -->
          <path d="M415 602L525 516L668 468L724 574L600 600L492 668" stroke="#2573db" stroke-opacity="0.22" stroke-width="1.1" stroke-dasharray="4 4" />
          <path d="M525 516L600 600L688 648" stroke="#14a398" stroke-opacity="0.24" stroke-width="1.1" />

          <!-- 协同关键节点与光环 -->
          <circle cx="415" cy="602" r="14" stroke="#2573db" stroke-opacity="0.24" />
          <circle cx="415" cy="602" r="5" fill="#2573db" fill-opacity="0.78" />
          <circle cx="525" cy="516" r="11" stroke="#14a398" stroke-opacity="0.28" />
          <circle cx="525" cy="516" r="4.5" fill="#14a398" fill-opacity="0.85" />
          <circle cx="600" cy="600" r="16" fill="#ffffff" fill-opacity="0.55" stroke="#2573db" stroke-opacity="0.34" />
          <circle cx="600" cy="600" r="6" fill="#2573db" fill-opacity="0.9" />
          <circle cx="668" cy="468" r="9" stroke="#2573db" stroke-opacity="0.22" />
          <circle cx="668" cy="468" r="3.5" fill="#2573db" fill-opacity="0.7" />
          <circle cx="724" cy="574" r="11" stroke="#14a398" stroke-opacity="0.24" />
          <circle cx="724" cy="574" r="4" fill="#14a398" fill-opacity="0.8" />
          <circle cx="492" cy="668" r="3.5" fill="#14a398" fill-opacity="0.6" />
          <circle cx="220" cy="672" r="4" fill="#2573db" fill-opacity="0.45" />
          <circle cx="220" cy="672" r="11" stroke="#2573db" stroke-opacity="0.18" />

          <!-- 坐标准星微装饰 -->
          <path d="M525 184v14M518 191h14" stroke="#2573db" stroke-opacity="0.24" stroke-width="1.2" />
          <path d="M686 278v12M680 284h12" stroke="#14a398" stroke-opacity="0.28" stroke-width="1.2" />
          <rect x="614" y="132" width="120" height="72" rx="12" fill="#ffffff" fill-opacity="0.32" stroke="#2573db" stroke-opacity="0.14" />
          <path d="M634 156h56M634 172h80M634 186h42" stroke="#2573db" stroke-opacity="0.22" stroke-width="2" stroke-linecap="round" />
        </svg>
      </div>
      <div class="story-foot"><span class="story-foot-line"></span> 数据驱动 <span class="story-foot-sep">/</span> 精准溯源</div>
    </section>

    <section class="login-panel" aria-labelledby="login-heading">
      <div class="login-panel-top"><span class="top-dot"></span> 业务系统登录</div>
      <div class="login-form-wrap">
        <div class="mobile-brand"><img :src="logo" alt="" /><span><strong>清源</strong><small>WELLSPRING</small></span></div>
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
      <div class="login-panel-foot"><span class="login-foot-brand">清源工作台 <span class="login-version">v{{ appVersion }}</span></span><span>安全 · 溯源 · 高效</span></div>
    </section>
  </main>
</template>
