<script setup lang="ts">
import {onBeforeUnmount,ref} from 'vue'
import FormDialog from '../../shared/components/FormDialog.vue'
import {useWorkspace} from '../../app/workspace'
import {isCancelled} from '../../shared/api/client'
import type {ActionSpec} from './types'
const props=defineProps<{spec:ActionSpec}>(),emit=defineEmits<{close:[];saved:[]}>()
const {command,captureSession}=useWorkspace(),busy=ref(false),error=ref(''),note=ref('')
let alive=true;onBeforeUnmount(()=>{alive=false})
async function save(){busy.value=true;error.value='';const valid=captureSession();try{await command('place-action-'+props.spec.path,props.spec.path,{version:props.spec.version,note:note.value,...props.spec.extra});if(alive&&valid())emit('saved')}catch(e){if(alive&&!isCancelled(e))error.value=e instanceof Error?e.message:'操作失败'}finally{if(alive)busy.value=false}}
</script>
<template><FormDialog :title="spec.title" :busy="busy" :error="error" @close="emit('close')"><form @submit.prevent="save"><label>办理意见 / 依据<textarea v-model="note" maxlength="2000" required></textarea></label><button :disabled="busy">确认办理</button></form></FormDialog></template>
