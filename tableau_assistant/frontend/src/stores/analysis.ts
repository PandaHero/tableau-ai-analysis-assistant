/**
 * Analysis Store
 * 管理分析状态
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAnalysisStore = defineStore('analysis', () => {
  const currentQuery = ref('')
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  function setQuery(query: string): void {
    currentQuery.value = query
  }

  function setLoading(loading: boolean): void {
    isLoading.value = loading
  }

  function setError(err: string | null): void {
    error.value = err
  }

  function reset(): void {
    currentQuery.value = ''
    isLoading.value = false
    error.value = null
  }

  return {
    currentQuery,
    isLoading,
    error,
    setQuery,
    setLoading,
    setError,
    reset
  }
})
