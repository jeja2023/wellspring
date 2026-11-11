<script setup lang="ts">
import { onBeforeUnmount, onMounted,ref } from 'vue'
import { useWorkspace } from '../../app/workspace'
import { createLatestRequests, isCancelled } from '../../shared/api/client'
const {api}=useWorkspace()
const pageRequests = createLatestRequests(api)
onBeforeUnmount(() => pageRequests.dispose())
const request = (path: string, options: RequestInit = {}) => pageRequests.latest(path.split('?')[0], path, options)
const loading=ref(false),error=ref(''),message=ref('')
async function check(){loading.value=true;error.value='';try{const result=await request('/ai/status');message.value=result.message}catch(e){if(isCancelled(e))return;error.value=e instanceof Error?e.message:'状态检查失败'}finally{loading.value=false}}
onMounted(check)
</script>
<template>

  <section class="card"><h2>服务状态</h2><p v-if="loading" role="status">正在检查…</p><p v-else-if="error" class="error" role="alert">{{error}}</p><div v-else class="warning">{{message}}</div><button class="secondary" :disabled="loading" @click="check">重新检查</button><p>接入本地服务并完成样本、权限和人工核验流程后，才可启用文件解析。模型结果须作为草稿，不直接写入正式事实。</p></section>
</template>
