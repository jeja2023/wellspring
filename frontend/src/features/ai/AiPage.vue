<script setup lang="ts">
import { onMounted,ref } from 'vue'
import { useWorkspace } from '../../app/workspace'
import { request } from '../../shared/api/client'
const {token}=useWorkspace()
const loading=ref(false),error=ref(''),message=ref('')
async function check(){loading.value=true;error.value='';try{const result=await request('/ai/status',token.value);message.value=result.message}catch(e){error.value=e instanceof Error?e.message:'状态检查失败'}finally{loading.value=false}}
onMounted(check)
</script>
<template>
  <div class="title-row"><p class="eyebrow">AI ASSISTANCE</p><h1>智能解析</h1><p class="muted">本地 OCR 与文书解析的服务状态。</p></div>
  <section class="card"><h2>服务状态</h2><p v-if="loading" role="status">正在检查…</p><p v-else-if="error" class="error" role="alert">{{error}}</p><div v-else class="warning">{{message}}</div><button class="secondary" :disabled="loading" @click="check">重新检查</button><p>接入本地服务并完成样本、权限和人工核验流程后，才可启用文件解析。模型结果须作为草稿，不直接写入正式事实。</p></section>
</template>
