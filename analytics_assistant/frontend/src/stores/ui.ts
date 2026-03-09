import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { ThemeManager } from '@/design-system/theme'

export type Theme = 'light' | 'dark' | 'auto'
export type LayoutMode = 'standard' | 'compact' | 'minimal'

export const useUiStore = defineStore('ui', () => {
  // 主题管理器
  const themeManager = ThemeManager.getInstance()
  
  // State
  const theme = ref<Theme>('auto')
  const windowWidth = ref(window.innerWidth)
  const isSettingsPanelOpen = ref(false)

  // Computed
  const layoutMode = computed<LayoutMode>(() => {
    if (windowWidth.value >= 768) return 'standard'
    if (windowWidth.value >= 480) return 'compact'
    return 'minimal'
  })

  const isTooSmall = computed(() => windowWidth.value < 320)

  const effectiveTheme = computed<'light' | 'dark'>(() => {
    if (theme.value === 'auto') {
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    }
    return theme.value
  })

  // Actions
  function setTheme(newTheme: Theme) {
    theme.value = newTheme
    themeManager.setTheme(newTheme)
  }

  function toggleTheme() {
    const current = theme.value
    const next = current === 'light' ? 'dark' : 'light'
    setTheme(next)
  }

  function applyTheme() {
    // 由 ThemeManager 处理
    themeManager.applyTheme()
  }
  
  function openSettingsPanel() {
    isSettingsPanelOpen.value = true
  }
  
  function closeSettingsPanel() {
    isSettingsPanelOpen.value = false
  }
  
  function toggleSettingsPanel() {
    isSettingsPanelOpen.value = !isSettingsPanelOpen.value
  }

  function handleResize() {
    windowWidth.value = window.innerWidth
  }

  function handleSystemThemeChange() {
    if (theme.value === 'auto') {
      applyTheme()
    }
  }

  // Initialize
  function init() {
    // 初始化主题管理器
    themeManager.init()
    
    // 同步主题状态
    theme.value = themeManager.getTheme()
    
    // 监听主题变化
    themeManager.onThemeChange((newTheme) => {
      theme.value = newTheme
    })

    // Listen for window resize
    window.addEventListener('resize', handleResize)

    // Listen for system theme changes
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', handleSystemThemeChange)
  }

  function cleanup() {
    window.removeEventListener('resize', handleResize)
    window.matchMedia('(prefers-color-scheme: dark)').removeEventListener('change', handleSystemThemeChange)
  }

  return {
    // State
    theme,
    windowWidth,
    isSettingsPanelOpen,
    // Computed
    layoutMode,
    isTooSmall,
    effectiveTheme,
    // Actions
    setTheme,
    toggleTheme,
    openSettingsPanel,
    closeSettingsPanel,
    toggleSettingsPanel,
    init,
    cleanup,
    // Aliases for App.vue compatibility
    setupListeners: init,
    cleanupListeners: cleanup
  }
})
