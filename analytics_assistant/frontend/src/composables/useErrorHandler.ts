/**
 * 错误处理 Composable
 * 提供统一的错误处理逻辑
 */

import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import type { ApiError } from '@/types'

export function useErrorHandler() {
  const { t } = useI18n()
  const error = ref<string | null>(null)
  const retryCallback = ref<(() => Promise<void>) | null>(null)

  /**
   * 处理错误
   */
  const handleError = (err: any, context?: string) => {
    console.error('Error:', err, 'Context:', context)

    // 提取错误消息
    let errorMessage = t('error.unknown')

    if (err.response) {
      // HTTP 错误
      const apiError = err.response.data as ApiError
      errorMessage = apiError.message || t(`error.http${err.response.status}`)
    } else if (err.message) {
      errorMessage = err.message
    }

    // 添加上下文
    if (context) {
      errorMessage = `${context}: ${errorMessage}`
    }

    error.value = errorMessage
    ElMessage.error(errorMessage)

    return errorMessage
  }

  /**
   * 重试操作
   */
  const retry = async () => {
    if (retryCallback.value) {
      try {
        clearError()
        await retryCallback.value()
      } catch (err) {
        handleError(err)
      }
    }
  }

  /**
   * 设置重试回调
   */
  const setRetryCallback = (callback: () => Promise<void>) => {
    retryCallback.value = callback
  }

  /**
   * 清除错误
   */
  const clearError = () => {
    error.value = null
  }

  return {
    error,
    handleError,
    retry,
    setRetryCallback,
    clearError
  }
}
