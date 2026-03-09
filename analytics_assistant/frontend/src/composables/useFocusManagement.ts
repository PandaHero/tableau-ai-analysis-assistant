/**
 * 焦点管理 Composable
 * 提供键盘导航和焦点陷阱功能
 */

import { ref, onMounted, onUnmounted } from 'vue'

export function useFocusManagement(containerRef: () => HTMLElement | undefined) {
  const focusableElements = ref<HTMLElement[]>([])
  const currentFocusIndex = ref(-1)

  /**
   * 获取所有可聚焦元素
   */
  const getFocusableElements = (): HTMLElement[] => {
    const container = containerRef()
    if (!container) return []

    const selector = [
      'a[href]',
      'button:not([disabled])',
      'textarea:not([disabled])',
      'input:not([disabled])',
      'select:not([disabled])',
      '[tabindex]:not([tabindex="-1"])'
    ].join(',')

    return Array.from(container.querySelectorAll(selector)) as HTMLElement[]
  }

  /**
   * 更新可聚焦元素列表
   */
  const updateFocusableElements = () => {
    focusableElements.value = getFocusableElements()
  }

  /**
   * 聚焦下一个元素
   */
  const focusNext = () => {
    updateFocusableElements()

    if (focusableElements.value.length === 0) return

    currentFocusIndex.value = (currentFocusIndex.value + 1) % focusableElements.value.length
    focusableElements.value[currentFocusIndex.value]?.focus()
  }

  /**
   * 聚焦上一个元素
   */
  const focusPrevious = () => {
    updateFocusableElements()

    if (focusableElements.value.length === 0) return

    currentFocusIndex.value =
      currentFocusIndex.value <= 0
        ? focusableElements.value.length - 1
        : currentFocusIndex.value - 1

    focusableElements.value[currentFocusIndex.value]?.focus()
  }

  /**
   * 焦点陷阱(用于模态框)
   */
  const trapFocus = (event: KeyboardEvent) => {
    if (event.key !== 'Tab') return

    updateFocusableElements()

    if (focusableElements.value.length === 0) {
      event.preventDefault()
      return
    }

    const firstElement = focusableElements.value[0]
    const lastElement = focusableElements.value[focusableElements.value.length - 1]

    if (event.shiftKey) {
      // Shift + Tab
      if (document.activeElement === firstElement) {
        event.preventDefault()
        lastElement.focus()
      }
    } else {
      // Tab
      if (document.activeElement === lastElement) {
        event.preventDefault()
        firstElement.focus()
      }
    }
  }

  /**
   * 启用焦点陷阱
   */
  const enableTrapFocus = () => {
    const container = containerRef()
    if (container) {
      container.addEventListener('keydown', trapFocus)
    }
  }

  /**
   * 禁用焦点陷阱
   */
  const disableTrapFocus = () => {
    const container = containerRef()
    if (container) {
      container.removeEventListener('keydown', trapFocus)
    }
  }

  // 组件挂载时更新可聚焦元素
  onMounted(() => {
    updateFocusableElements()
  })

  // 组件卸载时清理
  onUnmounted(() => {
    disableTrapFocus()
  })

  return {
    focusableElements,
    currentFocusIndex,
    focusNext,
    focusPrevious,
    trapFocus,
    enableTrapFocus,
    disableTrapFocus,
    updateFocusableElements
  }
}
