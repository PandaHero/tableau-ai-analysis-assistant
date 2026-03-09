/**
 * 键盘导航 Composable
 * 提供键盘快捷键和焦点管理功能
 */
import { onMounted, onUnmounted, ref } from 'vue'
import type { Ref } from 'vue'

export interface KeyboardShortcut {
  /**
   * 快捷键组合 (e.g., 'ctrl+k', 'escape', 'enter')
   */
  key: string
  
  /**
   * 是否需要 Ctrl 键
   */
  ctrl?: boolean
  
  /**
   * 是否需要 Shift 键
   */
  shift?: boolean
  
  /**
   * 是否需要 Alt 键
   */
  alt?: boolean
  
  /**
   * 是否需要 Meta 键 (Cmd on Mac)
   */
  meta?: boolean
  
  /**
   * 回调函数
   */
  handler: (event: KeyboardEvent) => void
  
  /**
   * 描述
   */
  description?: string
  
  /**
   * 是否阻止默认行为
   */
  preventDefault?: boolean
}

/**
 * 使用键盘导航
 * @param shortcuts 快捷键配置
 * @returns 键盘导航相关的状态和方法
 */
export function useKeyboardNavigation(shortcuts: KeyboardShortcut[] = []) {
  const isEnabled = ref(true)
  
  /**
   * 检查快捷键是否匹配
   */
  const matchesShortcut = (event: KeyboardEvent, shortcut: KeyboardShortcut): boolean => {
    const key = event.key.toLowerCase()
    const targetKey = shortcut.key.toLowerCase()
    
    // 检查主键
    if (key !== targetKey) return false
    
    // 检查修饰键
    if (shortcut.ctrl && !event.ctrlKey) return false
    if (shortcut.shift && !event.shiftKey) return false
    if (shortcut.alt && !event.altKey) return false
    if (shortcut.meta && !event.metaKey) return false
    
    // 确保没有额外的修饰键
    if (!shortcut.ctrl && event.ctrlKey) return false
    if (!shortcut.shift && event.shiftKey) return false
    if (!shortcut.alt && event.altKey) return false
    if (!shortcut.meta && event.metaKey) return false
    
    return true
  }
  
  /**
   * 键盘事件处理器
   */
  const handleKeyDown = (event: KeyboardEvent) => {
    if (!isEnabled.value) return
    
    for (const shortcut of shortcuts) {
      if (matchesShortcut(event, shortcut)) {
        if (shortcut.preventDefault !== false) {
          event.preventDefault()
        }
        shortcut.handler(event)
        break
      }
    }
  }
  
  /**
   * 启用键盘导航
   */
  const enable = () => {
    isEnabled.value = true
  }
  
  /**
   * 禁用键盘导航
   */
  const disable = () => {
    isEnabled.value = false
  }
  
  // 注册事件监听
  onMounted(() => {
    document.addEventListener('keydown', handleKeyDown)
  })
  
  onUnmounted(() => {
    document.removeEventListener('keydown', handleKeyDown)
  })
  
  return {
    isEnabled,
    enable,
    disable
  }
}

/**
 * 焦点管理
 */
export interface FocusTrapOptions {
  /**
   * 容器元素
   */
  container: Ref<HTMLElement | undefined>
  
  /**
   * 是否激活焦点陷阱
   */
  active?: Ref<boolean>
  
  /**
   * 初始焦点元素选择器
   */
  initialFocus?: string
  
  /**
   * 返回焦点元素
   */
  returnFocus?: HTMLElement
}

/**
 * 使用焦点陷阱
 * 用于模态框等需要限制焦点范围的场景
 */
export function useFocusTrap(options: FocusTrapOptions) {
  const { container, active, initialFocus, returnFocus } = options
  
  /**
   * 获取所有可聚焦元素
   */
  const getFocusableElements = (): HTMLElement[] => {
    if (!container.value) return []
    
    const selector = [
      'a[href]',
      'button:not([disabled])',
      'textarea:not([disabled])',
      'input:not([disabled])',
      'select:not([disabled])',
      '[tabindex]:not([tabindex="-1"])'
    ].join(',')
    
    return Array.from(container.value.querySelectorAll(selector))
  }
  
  /**
   * 处理 Tab 键
   */
  const handleTab = (event: KeyboardEvent) => {
    if (!active?.value || !container.value) return
    
    const focusableElements = getFocusableElements()
    if (focusableElements.length === 0) return
    
    const firstElement = focusableElements[0]
    const lastElement = focusableElements[focusableElements.length - 1]
    
    if (event.shiftKey) {
      // Shift + Tab: 向前导航
      if (document.activeElement === firstElement) {
        event.preventDefault()
        lastElement.focus()
      }
    } else {
      // Tab: 向后导航
      if (document.activeElement === lastElement) {
        event.preventDefault()
        firstElement.focus()
      }
    }
  }
  
  /**
   * 激活焦点陷阱
   */
  const activate = () => {
    if (!container.value) return
    
    // 保存当前焦点
    const previousFocus = document.activeElement as HTMLElement
    
    // 设置初始焦点
    if (initialFocus) {
      const element = container.value.querySelector(initialFocus) as HTMLElement
      element?.focus()
    } else {
      const focusableElements = getFocusableElements()
      focusableElements[0]?.focus()
    }
    
    // 注册 Tab 键监听
    document.addEventListener('keydown', handleTab)
    
    return () => {
      // 清理
      document.removeEventListener('keydown', handleTab)
      
      // 恢复焦点
      if (returnFocus) {
        returnFocus.focus()
      } else if (previousFocus) {
        previousFocus.focus()
      }
    }
  }
  
  /**
   * 停用焦点陷阱
   */
  const deactivate = () => {
    document.removeEventListener('keydown', handleTab)
  }
  
  return {
    activate,
    deactivate,
    getFocusableElements
  }
}

/**
 * 使用焦点指示器
 * 为键盘导航提供清晰的焦点指示
 */
export function useFocusIndicator() {
  const isKeyboardUser = ref(false)
  
  const handleMouseDown = () => {
    isKeyboardUser.value = false
    document.body.classList.remove('keyboard-user')
  }
  
  const handleKeyDown = (event: KeyboardEvent) => {
    if (event.key === 'Tab') {
      isKeyboardUser.value = true
      document.body.classList.add('keyboard-user')
    }
  }
  
  onMounted(() => {
    document.addEventListener('mousedown', handleMouseDown)
    document.addEventListener('keydown', handleKeyDown)
  })
  
  onUnmounted(() => {
    document.removeEventListener('mousedown', handleMouseDown)
    document.removeEventListener('keydown', handleKeyDown)
  })
  
  return {
    isKeyboardUser
  }
}

/**
 * 使用跳过链接
 * 提供跳过导航的快捷方式
 */
export function useSkipLink(targetId: string) {
  const skipToContent = () => {
    const target = document.getElementById(targetId)
    if (target) {
      target.focus()
      target.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }
  
  return {
    skipToContent
  }
}
