<script setup lang="ts">
import FormDialog from './FormDialog.vue'

withDefaults(
  defineProps<{
    open: boolean
    title: string
    message: string
    confirmText?: string
    danger?: boolean
    busy?: boolean
    error?: string
  }>(),
  { confirmText: '确认操作', danger: false, busy: false, error: '' }
)

const emit = defineEmits<{ close: []; confirm: [] }>()
</script>

<template>
  <FormDialog v-if="open" :title="title" :busy="busy" :error="error" @close="emit('close')">
    <p class="confirm-dialog-message">{{ message }}</p>
    <div class="confirm-dialog-actions">
      <button type="button" :class="{ 'btn-danger': danger }" :disabled="busy" @click="emit('confirm')">
        {{ busy ? '正在处理…' : confirmText }}
      </button>
    </div>
  </FormDialog>
</template>

