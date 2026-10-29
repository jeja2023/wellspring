<script setup lang="ts">
import { useWorkspace } from '../../app/workspace'
const { page } = useWorkspace()
</script>

<template>
<div class="title-row"><div><p class="eyebrow">PLANNED</p><h1>{{page}}</h1><p class="muted">此模块尚未实现，需先完成方案中的业务与权限确认。</p></div></div><div class="card empty-state"><div class="empty-icon">○</div><h2>功能建设中</h2><p>当前开发验证版本不提供此模块的业务操作。</p></div>
</template>
