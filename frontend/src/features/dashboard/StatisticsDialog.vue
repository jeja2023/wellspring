<script setup lang="ts">
import {onBeforeUnmount,ref,watch} from 'vue'
import {useWorkspace} from '../../app/workspace'
import FormDialog from '../../shared/components/FormDialog.vue'
import {formatTimestamp} from '../../shared/time'
import {statuses} from '../ai/types'
import {createInterpretation} from './interpretation'
const props=defineProps<{open:boolean;days:7|30|90;organization:string}>(),emit=defineEmits<{close:[]}>()
const {api,captureSession}=useWorkspace(),state=createInterpretation(api,captureSession)
const {service,active,days:period,consent,busy,checking,refreshing,error,pending,running,canGenerate,generate,cancel,refresh,check}=state
const notice=ref('')
watch(()=>props.open,value=>{notice.value='';if(value)state.enter(props.days);else state.leave()},{immediate:true})
onBeforeUnmount(state.dispose)
async function copy(){try{await navigator.clipboard.writeText(active.value?.output_text||'');notice.value='已复制解读内容'}catch{notice.value='当前浏览器无法复制，可直接选择解读文本复制'}}
</script>
<template>
  <FormDialog v-if="open" title="AI 统计解读" :wide="true" :busy="busy" :error="error" busy-message="正在处理，请稍候…" @close="emit('close')">
    <div class="statistics-meta"><span class="tag">近 {{period}} 天</span><span>{{organization}}</span><span v-if="active||service?.model">{{active?.model||service?.model}}</span><span v-if="active" class="tag">{{statuses[active.status]}}</span></div>
    <p class="muted statistics-note">根据提交时当前授权范围内的最新汇总统计生成解读，不包含业务原文和个人明细。</p>
    <p v-if="checking&&!service" class="muted" role="status">正在检查模型服务…</p>
    <p v-else-if="service&&!service.available" class="warning" role="status">{{service.message}}</p>
    <p v-if="running" class="muted" role="status">正在生成统计解读，可关闭弹窗后再打开查看。</p>
    <p v-if="active?.error_message" :class="active.status==='FAILED'?'error':'warning'" role="status">{{active.error_message}}</p>
    <p v-if="active?.truncated" class="warning">输出达到长度上限，解读内容可能不完整。</p>
    <div v-if="active?.output_text" class="statistics-result" tabindex="0">{{active.output_text}}</div>
    <p v-if="active?.output_text" class="muted statistics-note">生成于 {{formatTimestamp(active.completed_at||active.created_at)}} · 辅助解读结果，请结合业务核对。</p>
    <p v-if="notice" role="status" class="success">{{notice}}</p>
    <form v-if="!running" class="statistics-generate" @submit.prevent="generate">
      <label class="statistics-consent"><input v-model="consent" type="checkbox" required :disabled="busy||!service?.available">我已确认将汇总统计发送至已配置的模型服务。</label>
      <button :disabled="!canGenerate">{{busy?'正在提交…':pending?'重试提交':active?'重新生成解读':'生成统计解读'}}</button>
    </form>
    <div class="statistics-actions"><button v-if="running" type="button" class="secondary" :disabled="busy" @click="cancel">取消生成</button><button v-if="active" type="button" class="secondary" :disabled="busy||refreshing" @click="refresh">刷新结果</button><button v-if="active?.output_text" type="button" class="secondary" @click="copy">复制解读</button><button v-if="!service?.available" type="button" class="secondary" :disabled="checking||busy" @click="check">刷新服务状态</button></div>
  </FormDialog>
</template>
<style scoped>
.statistics-meta{display:flex;align-items:center;flex-wrap:wrap;gap:10px 16px}.statistics-note{font-size:12px;line-height:1.8}.statistics-result{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.9;background:#f7f9fb;border:1px solid #d8e1ea;border-radius:6px;padding:20px;max-height:48dvh;overflow:auto;margin:16px 0}.statistics-generate{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-top:20px}.statistics-consent{display:flex;align-items:flex-start;gap:8px;font-weight:400;line-height:1.8}.statistics-consent input{width:auto;flex:none;margin:5px 0 0}.statistics-actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px}
</style>
