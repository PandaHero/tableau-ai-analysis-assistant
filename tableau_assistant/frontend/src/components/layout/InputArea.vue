<template>
  <div class="input-area-content">
    <el-input
      v-model="inputText"
      type="textarea"
      :placeholder="placeholder"
      :disabled="disabled"
      :autosize="{ minRows: 1, maxRows: 4 }"
      :maxlength="maxLength"
      show-word-limit
      resize="none"
      @keydown="handleKeydown"
      ref="inputRef"
      class="message-input"
    />
    <el-button
      type="primary"
      :icon="Promotion"
      :disabled="!canSend"
      @click="handleSend"
      class="send-button"
      circle
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { Promotion } from '@element-plus/icons-vue'
import type { InputInstance } from 'element-plus'

const props = withDefaults(defineProps<{
  disabled?: boolean
  placeholder?: string
  maxLength?: number
}>(), {
  disabled: false,
  placeholder: '请输入您的数据分析问题...',
  maxLength: 2000
})

const emit = defineEmits<{
  send: [text: string]
}>()

const inputText = ref('')
const inputRef = ref<InputInstance>()

// 是否可以发送（非空且非纯空白）
const canSend = computed(() => {
  return !props.disabled && inputText.value.trim().length > 0
})

function handleKeydown(e: KeyboardEvent) {
  // Enter 发送，Shift+Enter 换行
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

function handleSend() {
  if (!canSend.value) return
  
  const text = inputText.value.trim()
  emit('send', text)
  inputText.value = ''
  
  // 保持焦点
  nextTick(() => {
    inputRef.value?.focus()
  })
}

// 暴露方法给父组件
function focus() {
  inputRef.value?.focus()
}

function clear() {
  inputText.value = ''
}

defineExpose({ focus, clear })
</script>

<style scoped>
.input-area-content {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  height: 100%;
}

.message-input {
  flex: 1;
}

.message-input :deep(.el-textarea__inner) {
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 14px;
  line-height: 1.5;
}

.message-input :deep(.el-textarea__inner:focus) {
  border-color: var(--tableau-blue);
  box-shadow: 0 0 0 2px rgba(31, 119, 180, 0.1);
}

.send-button {
  width: 34px;
  height: 34px;
  flex-shrink: 0;
}

.send-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
