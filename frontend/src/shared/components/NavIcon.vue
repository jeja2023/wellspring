<script setup lang="ts">
defineProps<{ name: string; size?: number }>()
</script>

<template>
  <svg
    class="ws-icon"
    :width="size || 16"
    :height="size || 16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.8"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <template v-if="name === '工作台'">
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
    </template>
    <template v-else-if="name === '数据大屏'">
      <path d="M3 3v18h18" />
      <path d="m19 9-5 5-4-4-3 3" />
    </template>
    <template v-else-if="name === '业务地图'">
      <polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21" />
      <line x1="9" y1="3" x2="9" y2="18" />
      <line x1="15" y1="6" x2="15" y2="21" />
    </template>
    <template v-else-if="name === '接警信息'">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
      <line x1="8" y1="13" x2="16" y2="13" />
      <line x1="8" y1="17" x2="13" y2="17" />
    </template>
    <template v-else-if="name === '案件管理'">
      <path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z" />
    </template>
    <template v-else-if="name === '情报线索'">
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.3-4.3" />
      <path d="M11 8v6M8 11h6" />
    </template>
    <template v-else-if="name === '人员档案'">
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </template>
    <template v-else-if="name === '重点场所'">
      <path d="M3 21h18" />
      <path d="M5 21V7l7-4 7 4v14" />
      <path d="M9 9v1M15 9v1M9 13v1M15 13v1M10 21v-4h4v4" />
    </template>
    <template v-else-if="name === '污水监测'">
      <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z" />
      <path d="M8.5 14.5a3.5 3.5 0 0 0 3.5 3.5" />
    </template>
    <template v-else-if="name === '智能研判'">
      <path d="M12 3l1.9 5.8L20 11l-6.1 2.2L12 19l-1.9-5.8L4 11l6.1-2.2z" />
    </template>
    <template v-else-if="name === '分析建模'">
      <circle cx="6" cy="6" r="2.5" />
      <circle cx="18" cy="6" r="2.5" />
      <circle cx="12" cy="18" r="2.5" />
      <path d="M8.2 7.5 11 15.8M15.8 7.5 13 15.8M8.5 6h7" />
    </template>
    <template v-else-if="name === '组织管理'">
      <rect x="9" y="3" width="6" height="5" rx="1" />
      <rect x="3" y="16" width="6" height="5" rx="1" />
      <rect x="15" y="16" width="6" height="5" rx="1" />
      <path d="M12 8v4M6 16v-4h12v4" />
    </template>
    <template v-else-if="name === '用户管理'">
      <circle cx="10" cy="8" r="4" />
      <path d="M2 20a6 6 0 0 1 12 0" />
      <path d="M17 11h5M19.5 8.5v5" />
    </template>
    <template v-else-if="name === '角色管理'">
      <path d="M12 2 4 5v6c0 5.2 3.4 9.9 8 11 4.6-1.1 8-5.8 8-11V5l-8-3Z" />
      <path d="m9 12 2 2 4-4" />
    </template>
    <template v-else-if="name === '权限管理'">
      <rect x="3" y="11" width="18" height="10" rx="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </template>
    <template v-else-if="name === '操作记录'">
      <circle cx="12" cy="12" r="9" />
      <polyline points="12 7 12 12 15.5 14" />
    </template>
    <template v-else-if="name === '系统日志'">
      <path d="M4 6h16M4 12h16M4 18h10" />
      <circle cx="18" cy="18" r="2" />
    </template>
    <template v-else-if="name === 'theme-light'">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </template>
    <template v-else-if="name === 'theme-dark'">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </template>
    <template v-else-if="name === 'theme-rail'">
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <line x1="9" y1="4" x2="9" y2="20" />
    </template>
    <template v-else-if="name === 'collapse'">
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M9 4v16M15 9l-3 3 3 3" />
    </template>
    <template v-else-if="name === 'expand'">
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M9 4v16M13 9l3 3-3 3" />
    </template>
    <template v-else-if="name === 'chevron-down'">
      <path d="m6 9 6 6 6-6" />
    </template>
    <template v-else-if="name === 'key'">
      <circle cx="7.5" cy="15.5" r="4.5" />
      <path d="m10.7 12.3 8.8-8.8M16.5 6.5l2.5 2.5M14 9l2 2" />
    </template>
    <template v-else-if="name === 'logout'">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <path d="m16 17 5-5-5-5M21 12H9" />
    </template>
    <template v-else>
      <circle cx="12" cy="12" r="4" />
    </template>
  </svg>
</template>

