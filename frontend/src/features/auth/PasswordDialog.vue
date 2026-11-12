<script setup lang="ts">
import {onBeforeUnmount,ref} from 'vue'
import {useWorkspace} from '../../app/workspace'
import FormDialog from '../../shared/components/FormDialog.vue'
const emit=defineEmits<{close:[]}>()
const {api,logout,captureSession}=useWorkspace(),oldPassword=ref(''),password=ref(''),confirm=ref(''),error=ref(''),busy=ref(false)
let mounted=true
onBeforeUnmount(()=>{mounted=false;oldPassword.value='';password.value='';confirm.value=''})
async function save(){const valid=captureSession();busy.value=true;error.value='';try{if(password.value!==confirm.value)throw new Error('两次新密码不一致');await api('/account/password',{method:'POST',body:JSON.stringify({old_password:oldPassword.value,password:password.value})});if(!mounted||!valid())return;await logout();emit('close')}catch(e){if(mounted&&valid())error.value=e instanceof Error?e.message:'修改失败'}finally{busy.value=false}}
</script>
<template><FormDialog title="修改密码" :busy="busy" :error="error" @close="emit('close')"><p>成功后将退出全部旧会话，请使用新密码登录。</p><form @submit.prevent="save"><label>原密码<input v-model="oldPassword" type="password" maxlength="256" required autocomplete="current-password"></label><label>新密码<input v-model="password" type="password" minlength="12" maxlength="256" required autocomplete="new-password"></label><label>确认新密码<input v-model="confirm" type="password" minlength="12" maxlength="256" required autocomplete="new-password"></label><button :disabled="busy">确认修改密码</button></form></FormDialog></template>
