<template>
  <Teleport to="#app">
    <div class="dialog-backdrop" @click.self="handleClose">
      <div class="dialog">
        <!-- 头部 -->
        <div class="dialog-header">
          <span class="dialog-title">添加自定义模型</span>
          <button class="dialog-close" @click="handleClose" aria-label="关闭">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M12 4L4 12M4 4l8 8" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/>
            </svg>
          </button>
        </div>

        <!-- 表单 -->
        <div class="dialog-body">
          <!-- 模型名称 -->
          <div class="form-field" :class="{ error: errors.name }">
            <label class="field-label">
              模型名称
              <span class="required">*</span>
            </label>
            <input
              v-model="form.name"
              class="field-input"
              type="text"
              placeholder="例如：My GPT-4"
              @blur="validate('name')"
              @input="clearError('name')"
            />
            <span v-if="errors.name" class="field-error">{{ errors.name }}</span>
          </div>

          <!-- API 地址 -->
          <div class="form-field" :class="{ error: errors.apiBase }">
            <label class="field-label">
              API 地址
              <span class="required">*</span>
            </label>
            <input
              v-model="form.apiBase"
              class="field-input"
              type="url"
              placeholder="https://api.example.com/v1"
              @blur="validate('apiBase')"
              @input="clearError('apiBase')"
            />
            <span v-if="errors.apiBase" class="field-error">{{ errors.apiBase }}</span>
          </div>

          <!-- API Key -->
          <div class="form-field">
            <label class="field-label">
              API Key
              <span class="optional">可选</span>
            </label>
            <div class="input-wrapper">
              <input
                v-model="form.apiKey"
                class="field-input"
                :type="showApiKey ? 'text' : 'password'"
                placeholder="sk-..."
              />
              <button class="toggle-eye" @click="showApiKey = !showApiKey" type="button">
                <svg v-if="!showApiKey" width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M8 3C4.5 3 1.5 6.5 1 8c.5 1.5 3.5 5 7 5s6.5-3.5 7-5c-.5-1.5-3.5-5-7-5Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>
                  <circle cx="8" cy="8" r="2" stroke="currentColor" stroke-width="1.4"/>
                </svg>
                <svg v-else width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M2 2l12 12M6.5 6.6A2 2 0 0 0 9.4 9.5M4.2 4.3C2.8 5.3 1.7 6.7 1 8c.5 1.5 3.5 5 7 5a7.2 7.2 0 0 0 3.8-1.1M7 3.1A7.4 7.4 0 0 1 8 3c3.5 0 6.5 3.5 7 5a9.5 9.5 0 0 1-1.7 2.6" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
                </svg>
              </button>
            </div>
          </div>

          <!-- 模型标识 -->
          <div class="form-field">
            <label class="field-label">
              模型标识
              <span class="optional">可选</span>
            </label>
            <input
              v-model="form.modelId"
              class="field-input"
              type="text"
              placeholder="例如：gpt-4o"
            />
            <span class="field-hint">部分 API 需要指定模型 ID</span>
          </div>

          <!-- 测试结果 -->
          <div v-if="testResult" class="test-result" :class="testResult.type">
            <svg v-if="testResult.type === 'success'" width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M2.5 7l3 3 6-6" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <svg v-else width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M7 4v3M7 9.5v.5" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/>
              <circle cx="7" cy="7" r="6" stroke="currentColor" stroke-width="1.4"/>
            </svg>
            {{ testResult.message }}
          </div>
        </div>

        <!-- 底部操作 -->
        <div class="dialog-footer">
          <button class="btn-test" @click="handleTest" :disabled="testing">
            <svg v-if="testing" class="spin-icon" width="14" height="14" viewBox="0 0 14 14" fill="none">
              <circle cx="7" cy="7" r="5.5" stroke="currentColor" stroke-width="1.5" stroke-dasharray="12 22"/>
            </svg>
            <svg v-else width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M7 1v2M7 11v2M1 7h2M11 7h2M2.8 2.8l1.4 1.4M9.8 9.8l1.4 1.4M2.8 11.2l1.4-1.4M9.8 4.2l1.4-1.4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
            </svg>
            {{ testing ? '测试中…' : '测试连接' }}
          </button>
          <div class="footer-right">
            <button class="btn-cancel" @click="handleClose">取消</button>
            <button class="btn-save" @click="handleSave">保存</button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import type { CustomModel } from '@/types'

const emit = defineEmits<{
  close: []
  save: [model: CustomModel]
}>()

const settingsStore = useSettingsStore()

const showApiKey = ref(false)
const testing = ref(false)
const testResult = ref<{ type: 'success' | 'error'; message: string } | null>(null)

const form = reactive({
  name: '',
  apiBase: '',
  apiKey: '',
  modelId: ''
})

const errors = reactive<Record<string, string>>({
  name: '',
  apiBase: ''
})

// ── 校验 ──
function validate(field: string): boolean {
  if (field === 'name') {
    if (!form.name.trim()) {
      errors.name = '请输入模型名称'
      return false
    }
    errors.name = ''
  }
  if (field === 'apiBase') {
    if (!form.apiBase.trim()) {
      errors.apiBase = '请输入 API 地址'
      return false
    }
    try {
      new URL(form.apiBase)
      errors.apiBase = ''
    } catch {
      errors.apiBase = '请输入有效的 URL'
      return false
    }
  }
  return true
}

function clearError(field: string) {
  errors[field] = ''
  testResult.value = null
}

function validateAll(): boolean {
  const nameOk = validate('name')
  const urlOk = validate('apiBase')
  return nameOk && urlOk
}

// ── 测试连接 ──
async function handleTest() {
  if (!validateAll()) return
  testing.value = true
  testResult.value = null
  try {
    const ok = await settingsStore.testCustomModel({
      name: form.name,
      apiBase: form.apiBase,
      apiKey: form.apiKey || undefined,
      modelId: form.modelId || undefined
    })
    testResult.value = ok
      ? { type: 'success', message: '连接成功！' }
      : { type: 'error', message: '连接失败，请检查 API 地址和 Key' }
  } catch {
    testResult.value = { type: 'error', message: '测试出错，请稍后重试' }
  } finally {
    testing.value = false
  }
}

// ── 保存 ──
function handleSave() {
  if (!validateAll()) return
  emit('save', {
    name: form.name.trim(),
    apiBase: form.apiBase.trim(),
    apiKey: form.apiKey.trim() || undefined,
    modelId: form.modelId.trim() || undefined
  })
}

function handleClose() {
  emit('close')
}
</script>

<style scoped lang="scss">
@use '@/assets/styles/variables.scss' as *;
@use '@/assets/styles/mixins.scss' as *;

// ── 遮罩 ──
.dialog-backdrop {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: $z-index-modal + 10;
  background-color: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(4px);
  @include flex-center;
  padding: $spacing-md;
}

// ── 对话框 ──
.dialog {
  width: 100%;
  max-width: 400px;
  background-color: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: $radius-md;
  box-shadow: $shadow-xl;
  display: flex;
  flex-direction: column;
  animation: dialogIn $transition-slow cubic-bezier(0.34, 1.56, 0.64, 1);
}

@keyframes dialogIn {
  from {
    opacity: 0;
    transform: scale(0.94) translateY(8px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}

// ── 头部 ──
.dialog-header {
  @include flex-between;
  padding: $spacing-md;
  border-bottom: 1px solid var(--border-color);
}

.dialog-title {
  font-size: $font-size-md;
  font-weight: $font-weight-semibold;
  color: var(--text-primary);
}

.dialog-close {
  @include flex-center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  color: var(--text-secondary);
  transition: all $transition-fast;

  &:hover {
    background-color: var(--bg-hover);
    color: var(--text-primary);
  }
}

// ── 表单 ──
.dialog-body {
  padding: $spacing-md;
  display: flex;
  flex-direction: column;
  gap: $spacing-md;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 5px;

  &.error .field-input {
    border-color: $color-error;

    &:focus {
      border-color: $color-error;
    }
  }
}

.field-label {
  @include flex-align-center;
  gap: 4px;
  font-size: $font-size-sm;
  font-weight: $font-weight-medium;
  color: var(--text-primary);
}

.required {
  color: $color-error;
  font-size: $font-size-xs;
}

.optional {
  font-size: 11px;
  color: var(--text-tertiary);
  font-weight: $font-weight-normal;
}

.field-input {
  @include input-base;
  width: 100%;
  font-size: $font-size-sm;
}

.input-wrapper {
  position: relative;
  display: flex;
  align-items: center;

  .field-input {
    padding-right: 36px;
  }
}

.toggle-eye {
  position: absolute;
  right: 10px;
  @include flex-center;
  width: 20px;
  height: 20px;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: color $transition-fast;

  &:hover {
    color: var(--text-secondary);
  }
}

.field-error {
  font-size: $font-size-xs;
  color: $color-error;
}

.field-hint {
  font-size: 11px;
  color: var(--text-tertiary);
}

// ── 测试结果 ──
.test-result {
  @include flex-align-center;
  gap: $spacing-xs;
  padding: 8px $spacing-sm;
  border-radius: $radius-sm;
  font-size: $font-size-xs;

  &.success {
    background-color: rgba(44, 160, 44, 0.1);
    color: $tableau-green;
    border: 1px solid rgba(44, 160, 44, 0.25);
  }

  &.error {
    background-color: rgba(214, 39, 40, 0.08);
    color: $tableau-red;
    border: 1px solid rgba(214, 39, 40, 0.2);
  }
}

// ── 底部 ──
.dialog-footer {
  @include flex-between;
  padding: $spacing-sm $spacing-md;
  border-top: 1px solid var(--border-color);
  gap: $spacing-sm;
}

.footer-right {
  @include flex-align-center;
  gap: $spacing-xs;
}

.btn-test {
  @include flex-align-center;
  gap: $spacing-xs;
  padding: 6px 12px;
  border-radius: $radius-sm;
  font-size: $font-size-sm;
  color: var(--text-secondary);
  border: 1px solid var(--border-color);
  background-color: var(--bg-secondary);
  cursor: pointer;
  transition: all $transition-fast;

  &:hover:not(:disabled) {
    border-color: var(--border-dark);
    color: var(--text-primary);
  }

  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
}

.btn-cancel {
  padding: 6px 14px;
  border-radius: $radius-sm;
  font-size: $font-size-sm;
  color: var(--text-secondary);
  transition: all $transition-fast;
  cursor: pointer;

  &:hover {
    background-color: var(--bg-hover);
    color: var(--text-primary);
  }
}

.btn-save {
  padding: 6px 16px;
  border-radius: $radius-sm;
  font-size: $font-size-sm;
  font-weight: $font-weight-medium;
  background-color: $tableau-blue;
  color: #fff;
  cursor: pointer;
  transition: opacity $transition-fast;

  &:hover {
    opacity: 0.88;
  }
}

// ── 旋转动画 ──
.spin-icon {
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
