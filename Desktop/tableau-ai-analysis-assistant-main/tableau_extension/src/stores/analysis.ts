import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { QueryResponse, SubTask } from '@/types'

export const useAnalysisStore = defineStore('analysis', () => {
  // 状态
  const currentQuery = ref<string>('')
  const isLoading = ref<boolean>(false)
  const queryResponse = ref<QueryResponse | null>(null)
  const error = ref<string | null>(null)

  // 方法
  const setQuery = (query: string) => {
    currentQuery.value = query
  }

  const setLoading = (loading: boolean) => {
    isLoading.value = loading
  }

  const setResponse = (response: QueryResponse) => {
    queryResponse.value = response
  }

  const setError = (err: string) => {
    error.value = err
  }

  const clearError = () => {
    error.value = null
  }

  const reset = () => {
    currentQuery.value = ''
    isLoading.value = false
    queryResponse.value = null
    error.value = null
  }

  return {
    // 状态
    currentQuery,
    isLoading,
    queryResponse,
    error,
    // 方法
    setQuery,
    setLoading,
    setResponse,
    setError,
    clearError,
    reset
  }
})
