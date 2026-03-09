/**
 * 虚拟滚动 Composable
 * 用于优化长列表性能
 */
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import type { Ref } from 'vue'

export interface VirtualScrollOptions {
  /**
   * 每项的高度(px)
   */
  itemHeight: number
  
  /**
   * 缓冲区大小(渲染可见区域外的项数)
   */
  buffer?: number
  
  /**
   * 容器高度(px),如果不提供则自动计算
   */
  containerHeight?: number
}

export interface VirtualScrollReturn<T> {
  /**
   * 可见的项列表
   */
  visibleItems: Ref<T[]>
  
  /**
   * 容器样式
   */
  containerStyle: Ref<Record<string, string>>
  
  /**
   * 内容样式
   */
  contentStyle: Ref<Record<string, string>>
  
  /**
   * 滚动到指定索引
   */
  scrollToIndex: (index: number) => void
  
  /**
   * 滚动到底部
   */
  scrollToBottom: () => void
  
  /**
   * 更新滚动位置
   */
  updateScroll: () => void
}

/**
 * 使用虚拟滚动
 * @param items 完整的项列表
 * @param containerRef 容器元素引用
 * @param options 配置选项
 * @returns 虚拟滚动相关的状态和方法
 */
export function useVirtualScroll<T>(
  items: Ref<T[]>,
  containerRef: Ref<HTMLElement | undefined>,
  options: VirtualScrollOptions
): VirtualScrollReturn<T> {
  const { itemHeight, buffer = 5, containerHeight: fixedHeight } = options

  // 滚动位置
  const scrollTop = ref(0)
  
  // 容器高度
  const containerHeight = ref(fixedHeight || 600)

  // 计算可见范围
  const visibleRange = computed(() => {
    const start = Math.floor(scrollTop.value / itemHeight)
    const visibleCount = Math.ceil(containerHeight.value / itemHeight)
    
    // 添加缓冲区
    const startIndex = Math.max(0, start - buffer)
    const endIndex = Math.min(items.value.length, start + visibleCount + buffer)
    
    return { startIndex, endIndex }
  })

  // 可见的项
  const visibleItems = computed(() => {
    const { startIndex, endIndex } = visibleRange.value
    return items.value.slice(startIndex, endIndex)
  })

  // 容器样式
  const containerStyle = computed(() => ({
    height: fixedHeight ? `${fixedHeight}px` : '100%',
    overflow: 'auto',
    position: 'relative'
  }))

  // 内容样式(用于占位,保持滚动条正确)
  const contentStyle = computed(() => {
    const totalHeight = items.value.length * itemHeight
    const { startIndex } = visibleRange.value
    const offsetY = startIndex * itemHeight
    
    return {
      height: `${totalHeight}px`,
      position: 'relative',
      transform: `translateY(${offsetY}px)`
    }
  })

  // 更新滚动位置
  const updateScroll = () => {
    if (!containerRef.value) return
    scrollTop.value = containerRef.value.scrollTop
  }

  // 滚动到指定索引
  const scrollToIndex = (index: number) => {
    if (!containerRef.value) return
    
    const targetIndex = Math.max(0, Math.min(index, items.value.length - 1))
    const targetScrollTop = targetIndex * itemHeight
    
    containerRef.value.scrollTop = targetScrollTop
    scrollTop.value = targetScrollTop
  }

  // 滚动到底部
  const scrollToBottom = () => {
    scrollToIndex(items.value.length - 1)
  }

  // 监听容器大小变化
  const updateContainerHeight = () => {
    if (!containerRef.value || fixedHeight) return
    containerHeight.value = containerRef.value.clientHeight
  }

  // 监听滚动事件
  let scrollHandler: (() => void) | null = null
  
  watch(containerRef, (newContainer, oldContainer) => {
    // 移除旧的事件监听
    if (oldContainer && scrollHandler) {
      oldContainer.removeEventListener('scroll', scrollHandler)
    }
    
    // 添加新的事件监听
    if (newContainer) {
      scrollHandler = updateScroll
      newContainer.addEventListener('scroll', scrollHandler, { passive: true })
      
      // 初始化容器高度
      updateContainerHeight()
    }
  })

  // 监听窗口大小变化
  let resizeObserver: ResizeObserver | null = null
  
  onMounted(() => {
    if (!fixedHeight && containerRef.value) {
      resizeObserver = new ResizeObserver(updateContainerHeight)
      resizeObserver.observe(containerRef.value)
    }
  })

  onUnmounted(() => {
    if (containerRef.value && scrollHandler) {
      containerRef.value.removeEventListener('scroll', scrollHandler)
    }
    
    if (resizeObserver) {
      resizeObserver.disconnect()
    }
  })

  return {
    visibleItems,
    containerStyle,
    contentStyle,
    scrollToIndex,
    scrollToBottom,
    updateScroll
  }
}
