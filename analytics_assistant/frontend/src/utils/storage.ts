import type { BoostPrompt } from '@/types'

/**
 * 本地存储工具
 */
export const storage = {
  /**
   * 获取存储的值
   * 
   * @param key - 存储键
   * @returns 解析后的值，如果不存在或解析失败则返回 null
   */
  get<T>(key: string): T | null {
    try {
      const item = localStorage.getItem(key)
      if (!item) {
        return null
      }
      return JSON.parse(item) as T
    } catch (err) {
      console.error(`读取 localStorage 失败 (key: ${key}):`, err)
      return null
    }
  },

  /**
   * 设置存储的值
   * 
   * @param key - 存储键
   * @param value - 要存储的值
   */
  set<T>(key: string, value: T): void {
    try {
      localStorage.setItem(key, JSON.stringify(value))
    } catch (err) {
      console.error(`写入 localStorage 失败 (key: ${key}):`, err)
    }
  },

  /**
   * 移除存储的值
   * 
   * @param key - 存储键
   */
  remove(key: string): void {
    try {
      localStorage.removeItem(key)
    } catch (err) {
      console.error(`删除 localStorage 失败 (key: ${key}):`, err)
    }
  },

  /**
   * 清空所有存储
   */
  clear(): void {
    try {
      localStorage.clear()
    } catch (err) {
      console.error('清空 localStorage 失败:', err)
    }
  }
}

/**
 * Boost Prompt 本地存储管理
 */
const BOOST_PROMPT_KEY = 'tableau_ai_custom_boost_prompts'

export const boostPromptStorage = {
  /**
   * 获取所有自定义快捷提示
   * 
   * @returns 自定义快捷提示数组
   */
  getAll(): BoostPrompt[] {
    return storage.get<BoostPrompt[]>(BOOST_PROMPT_KEY) || []
  },

  /**
   * 保存自定义快捷提示
   * 
   * @param prompts - 快捷提示数组
   */
  saveAll(prompts: BoostPrompt[]): void {
    storage.set(BOOST_PROMPT_KEY, prompts)
  },

  /**
   * 添加自定义快捷提示
   * 
   * @param prompt - 快捷提示对象
   */
  add(prompt: BoostPrompt): void {
    const prompts = this.getAll()
    prompts.push(prompt)
    this.saveAll(prompts)
  },

  /**
   * 更新自定义快捷提示
   * 
   * @param id - 快捷提示 ID
   * @param updates - 要更新的字段
   */
  update(id: string, updates: Partial<BoostPrompt>): void {
    const prompts = this.getAll()
    const index = prompts.findIndex((p) => p.id === id)
    if (index !== -1) {
      prompts[index] = { ...prompts[index], ...updates }
      this.saveAll(prompts)
    }
  },

  /**
   * 删除自定义快捷提示
   * 
   * @param id - 快捷提示 ID
   */
  delete(id: string): void {
    const prompts = this.getAll()
    const filtered = prompts.filter((p) => p.id !== id)
    this.saveAll(filtered)
  },

  /**
   * 清空所有自定义快捷提示
   */
  clear(): void {
    storage.remove(BOOST_PROMPT_KEY)
  }
}
