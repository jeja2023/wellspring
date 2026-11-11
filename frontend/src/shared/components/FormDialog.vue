<script setup lang="ts">
import {onBeforeUnmount,onMounted,ref} from 'vue'
const props=withDefaults(defineProps<{title:string;busy?:boolean;error?:string;wide?:boolean;busyMessage?:string}>(),{busy:false,error:'',wide:false,busyMessage:'正在保存，请稍候…'})
const emit=defineEmits<{close:[]}>(),dialog=ref<HTMLDialogElement|null>(null)
const previous=document.activeElement as HTMLElement|null
const previousOverflow=document.body.style.overflow
function close(){if(!props.busy)dialog.value?.close()}
onMounted(()=>{dialog.value?.showModal();document.body.style.overflow='hidden';dialog.value?.querySelector<HTMLElement>('input:not([type=hidden]),select,textarea')?.focus()})
onBeforeUnmount(()=>{dialog.value?.close();document.body.style.overflow=previousOverflow;if(previous?.isConnected)previous.focus()})
</script>
<template>
 <Teleport to="body"><dialog ref="dialog" class="form-dialog" :class="{'form-dialog-wide':wide}" :aria-label="title" :aria-busy="busy" @cancel="busy&&$event.preventDefault()" @close="emit('close')">
  <div class="form-dialog-heading"><h2>{{title}}</h2><button type="button" class="link" :disabled="busy" :aria-label="'关闭'+title" @click="close">关闭</button></div>
  <div class="form-dialog-body"><p v-if="error" class="error" role="alert">{{error}}</p><fieldset :disabled="busy"><slot /></fieldset></div>
  <div class="form-dialog-footer"><button type="button" class="secondary" :disabled="busy" @click="close">取消</button><span v-if="busy" class="muted" role="status">{{busyMessage}}</span></div>
 </dialog></Teleport>
</template>
