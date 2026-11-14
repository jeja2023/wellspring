<script setup lang="ts">
export type BadgeTone = 'neutral' | 'info' | 'success' | 'warning' | 'danger'
withDefaults(defineProps<{ tone?: BadgeTone }>(), { tone: 'neutral' })
</script>

<template>
  <span class="tag status-badge" :class="`is-${tone}`">
    <svg v-if="tone === 'warning' || tone === 'danger'" class="status-badge-glyph" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true">
      <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
      <path d="M12 9v4M12 17h.01" />
    </svg>
    <span v-else class="status-badge-dot" aria-hidden="true"></span>
    <slot />
  </span>
</template>

