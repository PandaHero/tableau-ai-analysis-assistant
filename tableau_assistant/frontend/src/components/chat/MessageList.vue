<template>
  <div class="message-list" ref="listRef" @scroll="handleScroll">
    <div class="messages-container">
      <!-- 虚拟滚动：当消息数量超过阈值时，只渲染可见区域的消息 -->
      <template v-if="useVirtualScroll">
        <!-- 顶部占位 -->
        <div :style="{ height: `${topPadding}px` }" />
        
        <!-- 可见消息 -->
        <template v-for="message in visibleMessages" :key="message.id">
          <div :ref="el => setMessageRef(message.id, el as HTMLElement)">
            <UserMessage 
              v-if="message.type === 'user'" 
              :message="message" 
            />
            <AIMessage 
              v-else-if="message.type === 'ai'" 
              :message="message" 
            />
            <SystemMessage 
              v-else-if="message.type === 'system'" 
              :message="message"
              @retry="$emit('retry')"
            />
          </div>
        </template>
        
        <!-- 底部占位 -->
        <div :style="{ height: `${bottomPadding}px` }" />
      </template>
      
      <!-- 普通渲染：消息数量较少时直接渲染所有消息 -->
      <template v-else>
        <template v-for="message in messages" :key="message.id">
          <UserMessage 
            v-if="message.type === 'user'" 
            :message="message" 
          />
          <AIMessage 
            v-else-if="message.type === 'ai'" 
            :message="message" 
          />
          <SystemMessage 
            v-else-if="message.type === 'system'" 
            :message="message"
            @retry="$emit('retry')"
          />
        </template>
      </template>
      
      <!-- 思考指示器：仅在处理中且没有流式内容时显示 -->
      <ThinkingIndicator 
        v-if="isProcessing && !hasStreamingContent" 
        :stage="processingStage" 
      />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * MessageList 组件
 * 
 * 支持虚拟滚动优化，当消息数量超过阈值时自动启用。
 * Task 21.2: 虚拟滚动实现
 * Requirements: NFR-1
 */
import { ref, watch, nextTick, computed, onMounted, onUnmounted } from 'vue'
import type { Message, ProcessingStage, AIMessage as AIMessageType } from '@/types'
import UserMessage from './UserMessage.vue'
import AIMessage from './AIMessage.vue'
import SystemMessage from './SystemMessage.vue'
import ThinkingIndicator from './ThinkingIndicator.vue'

const props = defineProps<{
  messages: Message[]
  isProcessing?: boolean
  processingStage?: ProcessingStage | null
}>()

defineEmits<{
  retry: []
}>()

// 虚拟滚动配置
const VIRTUAL_SCROLL_THRESHOLD = 50  // 消息数量超过此值时启用虚拟滚动
const ESTIMATED_ITEM_HEIGHT = 120    // 估算的消息高度
const BUFFER_SIZE = 5                // 上下缓冲区大小

const listRef = ref<HTMLElement | null>(null)
const scrollTop = ref(0)
const containerHeight = ref(0)

// 消息高度缓存
const messageHeights = ref<Map<string, number>>(new Map())

// 是否启用虚拟滚动
const useVirtualScroll = computed(() => props.messages.length > VIRTUAL_SCROLL_THRESHOLD)

/**
 * 检查是否有正在流式传输的消息（有内容）
 * 如果有，则不显示 ThinkingIndicator
 */
const hasStreamingContent = computed(() => {
  const lastMsg = props.messages[props.messages.length - 1]
  if (!lastMsg || lastMsg.type !== 'ai') return false
  const aiMsg = lastMsg as AIMessageType
  return aiMsg.isStreaming === true && !!aiMsg.content?.trim()
})

/**
 * 获取消息高度（使用缓存或估算值）
 */
function getMessageHeight(id: string): number {
  return messageHeights.value.get(id) || ESTIMATED_ITEM_HEIGHT
}

/**
 * 计算消息的累计偏移量
 */
function getMessageOffset(index: number): number {
  let offset = 0
  for (let i = 0; i < index; i++) {
    offset += getMessageHeight(props.messages[i].id) + 16 // 16px gap
  }
  return offset
}

/**
 * 计算总高度
 */
const totalHeight = computed(() => {
  if (!useVirtualScroll.value) return 0
  return props.messages.reduce((sum, msg) => sum + getMessageHeight(msg.id) + 16, 0)
})

/**
 * 计算可见消息范围
 */
const visibleRange = computed(() => {
  if (!useVirtualScroll.value) {
    return { start: 0, end: props.messages.length }
  }
  
  const viewportTop = scrollTop.value
  const viewportBottom = viewportTop + containerHeight.value
  
  // 二分查找起始位置
  let start = 0
  let offset = 0
  for (let i = 0; i < props.messages.length; i++) {
    const height = getMessageHeight(props.messages[i].id) + 16
    if (offset + height > viewportTop) {
      start = Math.max(0, i - BUFFER_SIZE)
      break
    }
    offset += height
  }
  
  // 查找结束位置
  let end = start
  offset = getMessageOffset(start)
  for (let i = start; i < props.messages.length; i++) {
    if (offset > viewportBottom + BUFFER_SIZE * ESTIMATED_ITEM_HEIGHT) {
      end = i
      break
    }
    offset += getMessageHeight(props.messages[i].id) + 16
    end = i + 1
  }
  
  return { start, end: Math.min(end + BUFFER_SIZE, props.messages.length) }
})

/**
 * 可见消息列表
 */
const visibleMessages = computed(() => {
  const { start, end } = visibleRange.value
  return props.messages.slice(start, end)
})

/**
 * 顶部占位高度
 */
const topPadding = computed(() => {
  if (!useVirtualScroll.value) return 0
  return getMessageOffset(visibleRange.value.start)
})

/**
 * 底部占位高度
 */
const bottomPadding = computed(() => {
  if (!useVirtualScroll.value) return 0
  const endOffset = getMessageOffset(visibleRange.value.end)
  return Math.max(0, totalHeight.value - endOffset)
})

/**
 * 设置消息元素引用，用于测量高度
 */
function setMessageRef(id: string, el: HTMLElement | null) {
  if (el) {
    nextTick(() => {
      const height = el.offsetHeight
      if (height > 0 && messageHeights.value.get(id) !== height) {
        messageHeights.value.set(id, height)
      }
    })
  }
}

/**
 * 处理滚动事件
 */
function handleScroll() {
  if (listRef.value) {
    scrollTop.value = listRef.value.scrollTop
  }
}

/**
 * 自动滚动到底部
 */
function scrollToBottom() {
  nextTick(() => {
    if (listRef.value) {
      listRef.value.scrollTop = listRef.value.scrollHeight
    }
  })
}

/**
 * 更新容器高度
 */
function updateContainerHeight() {
  if (listRef.value) {
    containerHeight.value = listRef.value.clientHeight
  }
}

// 监听消息变化，自动滚动
watch(() => props.messages.length, scrollToBottom)
watch(() => props.isProcessing, scrollToBottom)

// 监听窗口大小变化
onMounted(() => {
  updateContainerHeight()
  window.addEventListener('resize', updateContainerHeight)
})

onUnmounted(() => {
  window.removeEventListener('resize', updateContainerHeight)
})
</script>

<style scoped>
.message-list {
  height: 100%;
  overflow-y: auto;
  scroll-behavior: smooth;
}

.messages-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px 0;
  width: 100%;
}
</style>
