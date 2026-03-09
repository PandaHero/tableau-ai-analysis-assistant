/**
 * 防抖和节流 Composables
 * 用于性能优化
 */
import { ref, customRef } from 'vue'

/**
 * 防抖函数
 * @param fn 要防抖的函数
 * @param delay 延迟时间(ms)
 * @returns 防抖后的函数
 */
export function debounce<T extends (...args: any[]) => any>(
  fn: T,
  delay: number = 300
): (...args: Parameters<T>) => void {
  let timeoutId: ReturnType<typeof setTimeout> | null = null

  return function (this: any, ...args: Parameters<T>) {
    if (timeoutId) {
      clearTimeout(timeoutId)
    }

    timeoutId = setTimeout(() => {
      fn.apply(this, args)
      timeoutId = null
    }, delay)
  }
}

/**
 * 节流函数
 * @param fn 要节流的函数
 * @param delay 延迟时间(ms)
 * @returns 节流后的函数
 */
export function throttle<T extends (...args: any[]) => any>(
  fn: T,
  delay: number = 100
): (...args: Parameters<T>) => void {
  let lastCall = 0

  return function (this: any, ...args: Parameters<T>) {
    const now = Date.now()

    if (now - lastCall >= delay) {
      lastCall = now
      fn.apply(this, args)
    }
  }
}

/**
 * 防抖 Ref
 * 创建一个防抖的响应式引用
 * @param value 初始值
 * @param delay 延迟时间(ms)
 * @returns 防抖的 Ref
 */
export function useDebouncedRef<T>(value: T, delay: number = 300) {
  let timeoutId: ReturnType<typeof setTimeout> | null = null

  return customRef<T>((track, trigger) => {
    return {
      get() {
        track()
        return value
      },
      set(newValue: T) {
        if (timeoutId) {
          clearTimeout(timeoutId)
        }

        timeoutId = setTimeout(() => {
          value = newValue
          trigger()
          timeoutId = null
        }, delay)
      }
    }
  })
}

/**
 * 节流 Ref
 * 创建一个节流的响应式引用
 * @param value 初始值
 * @param delay 延迟时间(ms)
 * @returns 节流的 Ref
 */
export function useThrottledRef<T>(value: T, delay: number = 100) {
  let lastUpdate = 0

  return customRef<T>((track, trigger) => {
    return {
      get() {
        track()
        return value
      },
      set(newValue: T) {
        const now = Date.now()

        if (now - lastUpdate >= delay) {
          value = newValue
          lastUpdate = now
          trigger()
        }
      }
    }
  })
}

/**
 * 使用防抖的搜索
 * @param searchFn 搜索函数
 * @param delay 延迟时间(ms)
 * @returns 防抖的搜索函数和加载状态
 */
export function useDebouncedSearch<T>(
  searchFn: (query: string) => Promise<T>,
  delay: number = 300
) {
  const isSearching = ref(false)
  const results = ref<T | null>(null)
  const error = ref<Error | null>(null)

  const debouncedSearch = debounce(async (query: string) => {
    if (!query.trim()) {
      results.value = null
      return
    }

    isSearching.value = true
    error.value = null

    try {
      results.value = await searchFn(query)
    } catch (e) {
      error.value = e as Error
      results.value = null
    } finally {
      isSearching.value = false
    }
  }, delay)

  return {
    search: debouncedSearch,
    isSearching,
    results,
    error
  }
}
