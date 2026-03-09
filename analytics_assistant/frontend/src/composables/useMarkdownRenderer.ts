/**
 * Markdown 渲染 Composable
 * 提供防抖渲染逻辑
 */

import { ref, watch } from 'vue'
import { useDebounceFn } from '@vueuse/core'
import { renderMarkdown } from '@/utils/markdown'

export function useMarkdownRenderer(content: () => string, delay = 300) {
  const renderedContent = ref('')

  // 防抖渲染函数
  const debouncedRender = useDebounceFn(() => {
    const text = content()
    renderedContent.value = renderMarkdown(text)
  }, delay)

  // 监听内容变化
  watch(content, () => {
    debouncedRender()
  }, { immediate: true })

  return {
    renderedContent
  }
}
