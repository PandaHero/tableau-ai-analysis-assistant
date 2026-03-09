<template>
  <div class="input-area">
    <div class="input-shell">
      <div class="composer-meta">
        <span class="composer-meta__label">输入你的分析问题</span>
        <span class="composer-meta__hint">{{ disabled ? '正在处理上一条请求' : 'Enter 发送 / Shift + Enter 换行' }}</span>
      </div>

      <div class="input-wrapper">
        <textarea
          ref="textareaRef"
          v-model="inputText"
          class="input-textarea"
          :placeholder="placeholder"
          :disabled="disabled"
          :maxlength="maxLength"
          @keydown="handleKeydown"
          @input="handleInput"
        />

        <div class="input-actions">
          <div
            v-if="showCharCounter"
            class="char-counter"
            :class="charCounterClass"
          >
            {{ inputText.length }}/{{ maxLength }}
          </div>

          <button
            class="send-button"
            :disabled="!canSend"
            @click="handleSend"
            aria-label="发送"
          >
            <svg
              v-if="!disabled"
              class="send-button__icon"
              viewBox="0 0 20 20"
              fill="none"
            >
              <path
                d="M10 17V3M10 3L4 9M10 3l6 6"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>

            <svg
              v-else
              class="send-button__icon loading-icon"
              viewBox="0 0 20 20"
              fill="none"
            >
              <circle
                cx="10"
                cy="10"
                r="7"
                stroke-linecap="round"
                stroke-dasharray="40"
                stroke-dashoffset="18"
              />
            </svg>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, defineEmits, defineProps, nextTick, ref, watch } from 'vue'

interface Props {
  placeholder?: string
  disabled?: boolean
  maxLength?: number
  modelValue?: string
}

const props = withDefaults(defineProps<Props>(), {
  placeholder: '请输入您的问题...',
  disabled: false,
  maxLength: 2000,
  modelValue: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  send: [text: string]
}>()

const textareaRef = ref<HTMLTextAreaElement>()
const inputText = ref(props.modelValue)

watch(
  () => props.modelValue,
  (newValue) => {
    inputText.value = newValue
  },
)

watch(inputText, (newValue) => {
  emit('update:modelValue', newValue)
})

const canSend = computed(() => {
  if (props.disabled) {
    return false
  }

  const trimmed = inputText.value.trim()
  return trimmed.length > 0 && trimmed.length <= props.maxLength
})

const showCharCounter = computed(() => inputText.value.length > 0)

const charCounterClass = computed(() => {
  const length = inputText.value.length
  if (length >= props.maxLength) {
    return 'error'
  }

  if (length > props.maxLength - 120) {
    return 'warning'
  }

  return ''
})

function adjustHeight(): void {
  if (!textareaRef.value) {
    return
  }

  textareaRef.value.style.height = 'auto'
  const scrollHeight = textareaRef.value.scrollHeight
  const newHeight = Math.min(Math.max(scrollHeight, 48), 172)
  textareaRef.value.style.height = `${newHeight}px`
}

function handleInput(): void {
  adjustHeight()
}

function handleKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    if (canSend.value) {
      handleSend()
    }
  }

  if (event.key === 'Escape') {
    inputText.value = ''
    adjustHeight()
  }
}

function handleSend(): void {
  if (!canSend.value) {
    return
  }

  const text = inputText.value.trim()
  emit('send', text)
  inputText.value = ''
  nextTick(adjustHeight)
}

watch(
  textareaRef,
  () => {
    if (textareaRef.value) {
      adjustHeight()
    }
  },
  { immediate: true },
)
</script>

<style scoped lang="scss">
@use 'sass:color';
@use '@/assets/styles/variables.scss' as *;

.input-area {
  padding: 0 24px 18px;
  display: flex;
  justify-content: center;
  pointer-events: none;
}

.input-shell {
  width: 100%;
  max-width: 980px;
  pointer-events: auto;
}

.composer-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 10px 10px;
}

.composer-meta__label {
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.composer-meta__hint {
  color: var(--text-tertiary);
  font-size: 12px;
}

.input-wrapper {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  padding: 12px;
  border-radius: 30px;
  border: 1px solid rgba(15, 23, 42, 0.07);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(246, 248, 251, 0.96));
  box-shadow:
    0 16px 40px rgba(15, 23, 42, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.82);
  transition:
    border-color 180ms ease,
    box-shadow 180ms ease,
    transform 180ms ease;
}

.input-wrapper:focus-within {
  border-color: rgba(31, 119, 180, 0.2);
  box-shadow:
    0 18px 44px rgba(31, 119, 180, 0.10),
    0 0 0 4px rgba(31, 119, 180, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.82);
}

.input-textarea {
  min-height: 48px;
  max-height: 172px;
  width: 100%;
  padding: 6px 10px 6px 12px;
  border: none;
  background: transparent;
  resize: none;
  overflow-y: auto;
  color: var(--text-primary);
  font-size: 15px;
  line-height: 1.6;
}

.input-textarea:focus {
  outline: none;
}

.input-textarea:disabled {
  opacity: 0.72;
  cursor: not-allowed;
}

.input-textarea::placeholder {
  color: var(--text-tertiary);
}

.input-actions {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
}

.char-counter {
  min-width: 58px;
  padding: 6px 8px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.05);
  color: var(--text-tertiary);
  font-size: 11px;
  text-align: center;
}

.char-counter.warning {
  background: rgba(255, 127, 14, 0.10);
  color: var(--color-warning);
}

.char-counter.error {
  background: rgba(214, 39, 40, 0.10);
  color: var(--color-error);
}

.send-button {
  width: 48px;
  height: 48px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 16px;
  border: none;
  background: linear-gradient(135deg, #d9dee6, #cfd5de);
  color: #8c96a5;
  transition:
    transform 180ms ease,
    box-shadow 180ms ease,
    background 180ms ease,
    color 180ms ease;
}

.send-button:not(:disabled) {
  background: linear-gradient(135deg, $tableau-blue 0%, color.adjust($tableau-blue, $lightness: -10%) 100%);
  color: #fff;
  box-shadow:
    0 14px 24px rgba(31, 119, 180, 0.28),
    inset 0 1px 0 rgba(255, 255, 255, 0.18);
  cursor: pointer;
}

.send-button:hover:not(:disabled) {
  transform: translateY(-1px) scale(1.02);
  box-shadow:
    0 18px 28px rgba(31, 119, 180, 0.34),
    inset 0 1px 0 rgba(255, 255, 255, 0.2);
}

.send-button:active:not(:disabled) {
  transform: scale(0.96);
}

.send-button__icon {
  width: 20px;
  height: 20px;
  stroke: currentColor;
  stroke-width: 1.9;
}

.loading-icon {
  animation: spin 1s linear infinite;
}

:global([data-theme='dark']) .composer-meta__label {
  color: #d7dee8;
}

:global([data-theme='dark']) .input-wrapper {
  border-color: rgba(255, 255, 255, 0.08);
  background: linear-gradient(180deg, rgba(24, 28, 35, 0.98), rgba(20, 24, 31, 0.96));
  box-shadow:
    0 22px 44px rgba(0, 0, 0, 0.34),
    inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

:global([data-theme='dark']) .input-wrapper:focus-within {
  border-color: rgba(93, 173, 226, 0.28);
  box-shadow:
    0 24px 46px rgba(0, 0, 0, 0.42),
    0 0 0 4px rgba(31, 119, 180, 0.12),
    inset 0 1px 0 rgba(255, 255, 255, 0.05);
}

:global([data-theme='dark']) .char-counter {
  background: rgba(255, 255, 255, 0.06);
}

:global([data-theme='dark']) .send-button:disabled {
  background: linear-gradient(135deg, #414752, #373d47);
  color: #98a2b3;
}

@media (max-width: 767px) {
  .input-area {
    padding: 0 14px 14px;
  }

  .composer-meta {
    padding-inline: 6px;
  }

  .composer-meta__hint {
    display: none;
  }

  .input-wrapper {
    grid-template-columns: minmax(0, 1fr);
    border-radius: 24px;
  }

  .input-actions {
    flex-direction: row;
    justify-content: space-between;
  }

  .send-button {
    width: 44px;
    height: 44px;
    border-radius: 14px;
  }
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }

  to {
    transform: rotate(360deg);
  }
}
</style>
