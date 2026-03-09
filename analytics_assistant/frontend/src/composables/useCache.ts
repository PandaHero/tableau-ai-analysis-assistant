/**
 * 缓存 Composable
 * 提供内存缓存功能,支持 TTL 过期
 */

import { ref } from 'vue'

interface CacheEntry<T> {
  value: T
  expiresAt: number
}

export function useCache<T = any>(defaultTTL = 5 * 60 * 1000) {
  const cache = ref<Map<string, CacheEntry<T>>>(new Map())

  /**
   * 获取缓存
   */
  const get = (key: string): T | null => {
    const entry = cache.value.get(key)

    if (!entry) {
      return null
    }

    // 检查是否过期
    if (Date.now() > entry.expiresAt) {
      cache.value.delete(key)
      return null
    }

    return entry.value
  }

  /**
   * 设置缓存
   */
  const set = (key: string, value: T, ttl = defaultTTL) => {
    const expiresAt = Date.now() + ttl

    cache.value.set(key, {
      value,
      expiresAt
    })
  }

  /**
   * 删除缓存
   */
  const remove = (key: string) => {
    cache.value.delete(key)
  }

  /**
   * 清空所有缓存
   */
  const clear = () => {
    cache.value.clear()
  }

  /**
   * 检查缓存是否存在且未过期
   */
  const has = (key: string): boolean => {
    return get(key) !== null
  }

  /**
   * 获取缓存大小
   */
  const size = (): number => {
    // 清理过期缓存
    const now = Date.now()
    for (const [key, entry] of cache.value.entries()) {
      if (now > entry.expiresAt) {
        cache.value.delete(key)
      }
    }

    return cache.value.size
  }

  /**
   * 获取或设置缓存(如果不存在则执行 factory 函数)
   */
  const getOrSet = async (
    key: string,
    factory: () => Promise<T>,
    ttl = defaultTTL
  ): Promise<T> => {
    const cached = get(key)

    if (cached !== null) {
      return cached
    }

    const value = await factory()
    set(key, value, ttl)

    return value
  }

  return {
    get,
    set,
    remove,
    clear,
    has,
    size,
    getOrSet
  }
}
