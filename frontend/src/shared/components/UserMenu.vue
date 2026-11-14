<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import NavIcon from './NavIcon.vue'

const props = defineProps<{
  username: string
  organization: string
  roleName?: string
}>()

const emit = defineEmits<{
  password: []
  logout: []
}>()

const open = ref(false)
const rootRef = ref<HTMLElement | null>(null)
const triggerRef = ref<HTMLButtonElement | null>(null)

const initial = computed(() => (props.username.trim().slice(0, 1) || '用').toUpperCase())
const identityTitle = computed(() => [props.organization, props.username, props.roleName].filter(Boolean).join(' · '))

function closeMenu(restoreFocus = false) {
  if (!open.value) return
  open.value = false
  if (restoreFocus) triggerRef.value?.focus()
}

function toggleMenu() {
  open.value = !open.value
}

function handlePassword() {
  closeMenu()
  emit('password')
}

function handleLogout() {
  closeMenu()
  emit('logout')
}

function onPointerDown(event: PointerEvent) {
  if (!open.value) return
  if (rootRef.value && event.target instanceof Node && !rootRef.value.contains(event.target)) closeMenu()
}

function onKeyDown(event: KeyboardEvent) {
  if (event.key === 'Escape' && open.value) {
    event.preventDefault()
    closeMenu(true)
  }
}

watch(() => props.username, () => closeMenu())

onMounted(() => {
  document.addEventListener('pointerdown', onPointerDown)
  document.addEventListener('keydown', onKeyDown)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onPointerDown)
  document.removeEventListener('keydown', onKeyDown)
})
</script>

<template>
  <div ref="rootRef" class="user-menu">
    <button
      ref="triggerRef"
      type="button"
      class="user-menu-trigger"
      aria-label="当前账号菜单"
      aria-haspopup="true"
      :aria-expanded="open"
      :title="identityTitle"
      @click="toggleMenu"
    >
      <span class="user-avatar" aria-hidden="true">{{ initial }}</span>
      <span class="user-trigger-name">{{ username }}</span>
      <NavIcon name="chevron-down" :size="14" class="user-chevron" :class="{ 'is-open': open }" />
    </button>

    <div v-if="open" class="user-menu-popover" role="region" aria-label="账号信息与操作">
      <div class="user-menu-profile">
        <span class="user-avatar is-lg" aria-hidden="true">{{ initial }}</span>
        <div class="user-menu-meta">
          <div class="user-menu-name-row">
            <strong>{{ username }}</strong>
            <span v-if="roleName" class="header-role-pill">{{ roleName }}</span>
          </div>
          <div class="user-menu-org">{{ organization }}</div>
        </div>
      </div>
      <div class="user-menu-sep" aria-hidden="true"></div>
      <button type="button" class="user-menu-item" @click="handlePassword">
        <NavIcon name="key" :size="15" />
        <span>修改密码</span>
      </button>
      <button type="button" class="user-menu-item is-danger" @click="handleLogout">
        <NavIcon name="logout" :size="15" />
        <span>退出</span>
      </button>
    </div>
  </div>
</template>

