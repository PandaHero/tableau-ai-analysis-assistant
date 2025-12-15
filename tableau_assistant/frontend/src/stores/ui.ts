import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export type Theme = 'light' | 'dark' | 'system'
export type LayoutMode = 'standard' | 'compact' | 'minimal'

export const useUiStore = defineStore('ui', () => {
  // State
  const theme = ref<Theme>('system')
  const windowWidth = ref(window.innerWidth)

  // Computed
  const layoutMode = computed<LayoutMode>(() => {
    if (windowWidth.value >= 768) return 'standard'
    if (windowWidth.value >= 480) return 'compact'
    return 'minimal'
  })

  const isTooSmall = computed(() => windowWidth.value < 320)

  const effectiveTheme = computed<'light' | 'dark'>(() => {
    if (theme.value === 'system') {
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    }
    return theme.value
  })

  // Actions
  function setTheme(newTheme: Theme) {
    theme.value = newTheme
    localStorage.setItem('ui-theme', newTheme)
    applyTheme()
  }

  function applyTheme() {
    const root = document.documentElement
    if (effectiveTheme.value === 'dark') {
      root.classList.add('dark')
    } else {
      root.classList.remove('dark')
    }
  }

  function handleResize() {
    windowWidth.value = window.innerWidth
  }

  function handleSystemThemeChange() {
    if (theme.value === 'system') {
      applyTheme()
    }
  }

  // Initialize
  function init() {
    // Load saved theme
    const savedTheme = localStorage.getItem('ui-theme') as Theme | null
    if (savedTheme && ['light', 'dark', 'system'].includes(savedTheme)) {
      theme.value = savedTheme
    }
    applyTheme()

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
    // Computed
    layoutMode,
    isTooSmall,
    effectiveTheme,
    // Actions
    setTheme,
    init,
    cleanup,
    // Aliases for App.vue compatibility
    setupListeners: init,
    cleanupListeners: cleanup
  }
})
