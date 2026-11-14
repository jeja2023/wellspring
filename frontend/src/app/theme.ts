import { ref } from 'vue'

export type ThemeMode = 'light' | 'ocean' | 'dark'
export type SidebarMode = 'expanded' | 'rail'

const THEME_KEY = 'wellspring.ui.theme.v2'
const SIDEBAR_KEY = 'wellspring.ui.sidebar'

export const themeLabels: Record<ThemeMode, string> = {
  light: '清朗浅白',
  ocean: '柔雾天蓝',
  dark: '柔和暗夜',
}

function readStorage<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  try {
    const raw = globalThis.localStorage?.getItem(key)
    if (raw && (allowed as readonly string[]).includes(raw)) return raw as T
  } catch {
    /* 离线受限环境允许忽略本地存储 */
  }
  return fallback
}

function writeStorage(key: string, value: string) {
  try {
    globalThis.localStorage?.setItem(key, value)
  } catch {
    /* 仅内存保持当前偏好 */
  }
}

const theme = ref<ThemeMode>(readStorage(THEME_KEY, ['light', 'ocean', 'dark'] as const, 'light'))
const sidebar = ref<SidebarMode>(readStorage(SIDEBAR_KEY, ['expanded', 'rail'] as const, 'expanded'))

export function applyThemeAttributes() {
  const root = globalThis.document?.documentElement
  if (!root) return
  root.setAttribute('data-theme', theme.value)
  root.removeAttribute('data-density')
  root.setAttribute('data-sidebar', sidebar.value)
}

export function setThemeMode(next: ThemeMode) {
  theme.value = next
  writeStorage(THEME_KEY, next)
  applyThemeAttributes()
}

export function cycleThemeMode() {
  const order: ThemeMode[] = ['light', 'ocean', 'dark']
  setThemeMode(order[(order.indexOf(theme.value) + 1) % order.length])
}

export function setSidebarMode(next: SidebarMode) {
  sidebar.value = next
  writeStorage(SIDEBAR_KEY, next)
  applyThemeAttributes()
}

export function toggleSidebarMode() {
  setSidebarMode(sidebar.value === 'expanded' ? 'rail' : 'expanded')
}

export function useThemePreferences() {
  return {
    theme,
    sidebar,
    setThemeMode,
    cycleThemeMode,
    setSidebarMode,
    toggleSidebarMode,
  }
}
