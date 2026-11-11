<script setup lang="ts">
import {onBeforeUnmount,onMounted,reactive,ref,watch} from 'vue'
import {useWorkspace} from '../../app/workspace'
import {createLatestRequests,isCancelled} from '../../shared/api/client'
import {formatTimestamp} from '../../shared/time'
import type {AiSettings} from './types'
import FormDialog from '../../shared/components/FormDialog.vue'
import './ai.css'
const {api,command,captureSession}=useWorkspace(),requests=createLatestRequests(api)
const emit=defineEmits<{close:[];saved:[]}>()
const settings=ref<AiSettings|null>(null),busy=ref(false),error=ref(''),notice=ref(''),modelIds=ref<string[]>([]),showKey=ref(false)
const form=reactive({version:0,enabled:false,base_url:'',model:'',timeout_seconds:60,max_output_tokens:2048,token_parameter:'max_tokens' as 'max_tokens'|'max_completion_tokens',api_key:'',api_key_action:'keep' as 'keep'|'replace'|'clear'|'environment'})
watch(()=>form.api_key,value=>{if(value)form.api_key_action='replace';else if(form.api_key_action==='replace')form.api_key_action='keep'})
watch(()=>form.base_url,()=>{modelIds.value=[]})
async function load(){const result=await requests.latest<AiSettings>('settings','/system/ai');settings.value=result;Object.assign(form,{version:result.version,enabled:result.enabled,base_url:result.base_url,model:result.model,timeout_seconds:result.timeout_seconds,max_output_tokens:result.max_output_tokens,token_parameter:result.token_parameter,api_key:'',api_key_action:'keep'});showKey.value=false;modelIds.value=[]}
async function act(task:()=>Promise<void>){busy.value=true;error.value='';notice.value='';try{await task()}catch(e){if(!isCancelled(e))error.value=e instanceof Error?e.message:'操作失败'}finally{busy.value=false}}
async function save(){await act(async()=>{const valid=captureSession();const result=await command('ai-service','/system/ai/update',{...form}) as AiSettings;if(!valid())return;settings.value=result;form.version=result.version;form.api_key='';form.api_key_action='keep';showKey.value=false;emit('saved')})}
async function check(){await act(async()=>{const valid=captureSession();const result=await api<{ok:boolean;message:string;duration_ms:number}>('/system/ai/test',{method:'POST',body:JSON.stringify({...form}),timeoutMs:135000});if(!valid())return;if(result.ok)notice.value=result.message+`（${(result.duration_ms/1000).toFixed(1)} 秒）；当前填写内容尚需保存后生效。`;else error.value=result.message})}
async function fetchModels(){await act(async()=>{const valid=captureSession();const result=await api<{ids:string[];message:string}>('/system/ai/models',{method:'POST',body:JSON.stringify({...form}),timeoutMs:135000});if(!valid())return;modelIds.value=result.ids;if(result.ids.length===1&&!form.model)form.model=result.ids[0];notice.value=result.message+'；请选择支持文本生成的模型，列表获取不会保存配置。'})}
function clearKey(){form.api_key='';form.api_key_action='clear';showKey.value=false}
function environmentKey(){form.api_key='';form.api_key_action='environment';showKey.value=false}
onMounted(()=>{void act(load)});onBeforeUnmount(()=>{requests.dispose();form.api_key=''})
</script>
<template>
  <FormDialog title="配置模型服务" :wide="true" :busy="busy" :error="error" busy-message="正在处理，请稍候…" @close="emit('close')"><div class="ai-settings"><p v-if="notice" class="success" role="status">{{notice}}</p><div class="page-toolbar page-toolbar-actions"><button class="secondary" :disabled="busy" @click="act(load)">重新加载</button></div>
    <form @submit.prevent="save"><fieldset :disabled="busy" class="ai-form-fields"><label class="check-label"><input v-model="form.enabled" type="checkbox">启用模型服务</label><div class="ai-settings-fields">
      <label>接口根地址<input v-model="form.base_url" type="url" maxlength="1000" :required="form.enabled" placeholder="http://127.0.0.1:8001/v1"></label>
      <div class="ai-key-field"><label>API Key<input v-model="form.api_key" :type="showKey?'text':'password'" maxlength="16384" autocomplete="new-password" spellcheck="false" :placeholder="settings?.api_key_configured?'已配置，留空保留原密钥':'无需鉴权的本地服务可留空'"></label><div class="ai-key-actions"><button type="button" class="link" :disabled="!form.api_key" @click="showKey=!showKey">{{showKey?'隐藏输入':'显示输入'}}</button><button type="button" class="link" @click="clearKey">清除密钥</button><button type="button" class="link" @click="environmentKey">使用环境配置</button></div><p class="muted ai-hint">{{form.api_key_action==='replace'?'待保存新密钥':form.api_key_action==='clear'?'待保存：清除当前密钥并停用环境密钥':form.api_key_action==='environment'?'待保存：改用服务端环境密钥':settings?.api_key_configured?'已配置（不回显）':'未配置密钥'}}</p></div>
      <label>模型名称<input v-model="form.model" maxlength="200" :required="form.enabled" placeholder="获取后选择模型 ID，也可手动填写"></label>
      <label v-if="modelIds.length">可用模型 ID<select :value="form.model" @change="form.model=($event.target as HTMLSelectElement).value"><option value="" disabled>选择文本生成模型</option><option v-for="id in modelIds" :key="id" :value="id">{{id}}</option></select></label>
      <label>请求超时（秒）<input v-model.number="form.timeout_seconds" type="number" min="5" max="120" required></label><label>最大输出 Token<input v-model.number="form.max_output_tokens" type="number" min="128" max="8192" required></label><label>输出长度参数<select v-model="form.token_parameter"><option value="max_tokens">max_tokens（常见兼容服务）</option><option value="max_completion_tokens">max_completion_tokens</option></select></label>
    </div>
    <div class="actions ai-test-actions"><button type="button" class="secondary" :disabled="busy||!form.base_url" @click="fetchModels">获取模型列表</button><button type="button" class="secondary" :disabled="busy||!form.base_url||!form.model" @click="check">测试模型连接</button></div>
    <p class="muted ai-hint">获取模型和测试连接均使用当前填写的地址、API Key 和模型，无须先保存；不会发送业务资料。服务不支持模型列表时，可直接手动填写模型 ID 并测试。</p><div class="ai-connection-details"><p class="muted">保存后密钥只存放在服务端受控目录，页面不会读取原密钥。留空保留原值，点击“清除密钥”或“使用环境配置”后需保存生效。</p><p class="muted">允许连接的主机：{{settings?.allowed_hosts.join('、')||'正在加载…'}}。新增内网/外部主机需修改服务端允许名单后重启。</p><p v-if="settings?.checked_at" class="muted">最近已保存配置检查：{{formatTimestamp(settings.checked_at)}} · {{settings.check_message}}</p></div></fieldset><div class="actions"><button :disabled="busy">保存配置</button></div></form>
  </div></FormDialog>
</template>
