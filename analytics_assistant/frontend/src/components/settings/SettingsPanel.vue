<template>
  <!-- 遮罩层 -->
  <Transition name="backdrop">
    <div
      v-if="props.open"
      class="settings-backdrop"
      @click="handleClose"
    />
  </Transition>

  <!-- 设置面板 -->
  <Transition name="slide">
    <div v-if="props.open" id="settings-panel" class="settings-panel" role="dialog" aria-modal="true" aria-label="设置面板">
      <!-- 头部 -->
      <div class="settings-header">
        <div class="header-left">
          <svg class="header-icon" width="18" height="18" viewBox="0 0 18 18" fill="none">
            <circle cx="9" cy="9" r="2.5" stroke="#1F77B4" stroke-width="1.5"/>
            <path d="M9 1v2M9 15v2M1 9h2M15 9h2M3.05 3.05l1.41 1.41M13.54 13.54l1.41 1.41M3.05 14.95l1.41-1.41M13.54 4.46l1.41-1.41" stroke="#1F77B4" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
          <span class="header-title">设置</span>
        </div>
        <button class="close-btn" @click="handleClose" aria-label="关闭">
          <img :src="closeIconUrl" class="close-btn__icon" alt="" aria-hidden="true" />
        </button>
      </div>

      <!-- 内容 -->
      <div class="settings-body">

        <!-- ── 数据配置 ── -->
        <section class="settings-section">
          <div class="section-label">数据配置</div>

          <div class="setting-item">
            <label class="setting-label">
              <span class="label-icon">📊</span>
              <span>数据源</span>
            </label>
            <select
              v-model="selectedDatasourceValue"
              class="setting-select"
            >
              <option value="__AUTO__">自动检测</option>
              <option
                v-for="name in datasourceOptions"
                :key="name"
                :value="name"
              >
                {{ name }}
              </option>
            </select>
          </div>

          <div class="setting-item">
            <label class="setting-label">
              <span class="label-icon">🔍</span>
              <span>分析深度</span>
            </label>
            <div class="depth-cards">
              <button
                v-for="opt in DEPTH_OPTIONS"
                :key="opt.value"
                class="depth-card"
                :class="{ active: analysisDepth === opt.value }"
                @click="analysisDepth = opt.value"
              >
                <span class="depth-name">{{ opt.label }}</span>
                <span class="depth-desc">{{ opt.desc }}</span>
              </button>
            </div>
            <div class="setting-hint">
              💡 标准模式适合快速获取答案，深入分析会进行多轮探索
            </div>
          </div>
        </section>

        <!-- ── AI 配置 ── -->
        <section class="settings-section">
          <div class="section-label">AI 配置</div>

          <div class="setting-item">
            <label class="setting-label">
              <span class="label-icon">🤖</span>
              <span>AI 模型</span>
            </label>
            <select v-model="selectedModel" class="setting-select">
              <option
                v-for="model in settingsStore.allModels"
                :key="model.id"
                :value="model.id"
              >
                {{ model.name }}{{ model.isCustom ? ' (自定义)' : '' }}
              </option>
            </select>
          </div>

          <button class="add-model-btn" @click="showAddModel = true">
            <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
              <path d="M6.5 1v11M1 6.5h11" stroke="#1F77B4" stroke-width="1.75" stroke-linecap="round"/>
            </svg>
            添加自定义模型
          </button>
        </section>

        <!-- ── 界面设置 ── -->
        <section class="settings-section">
          <div class="section-label">界面设置</div>

          <div class="setting-row-grid">
            <!-- 语言 -->
            <div class="setting-item">
              <label class="setting-label">
                <span class="label-icon">🌐</span>
                <span>语言</span>
              </label>
              <select v-model="language" class="setting-select">
                <option value="zh">中文</option>
                <option value="en">English</option>
              </select>
            </div>

            <!-- 主题 -->
            <div class="setting-item">
              <label class="setting-label">
                <span class="label-icon">🎨</span>
                <span>主题</span>
              </label>
              <div class="theme-group">
                <button
                  v-for="opt in THEME_OPTIONS"
                  :key="opt.value"
                  class="theme-btn"
                  :class="{ active: theme === opt.value }"
                  @click="theme = opt.value"
                  :title="opt.label"
                >
                  <span>{{ opt.icon }}</span>
                  <span class="theme-label">{{ opt.label }}</span>
                </button>
              </div>
            </div>
          </div>
        </section>

      </div>

      <!-- 底部 -->
      <div class="settings-footer">
        <button class="reset-btn" @click="handleReset">
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
            <path d="M1.5 6.5a5 5 0 1 0 .9-2.8M1.5 1v3.5h3.5" stroke="#666666" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          恢复默认
        </button>
        <span class="version-text">Tableau AI 助手</span>
      </div>
    </div>
  </Transition>

  <!-- 添加自定义模型对话框 -->
  <CustomModelDialog
    v-if="showAddModel"
    @close="showAddModel = false"
    @save="handleModelSaved"
  />
</template>

<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import { useUiStore } from '@/stores/ui'
import { useTableauStore } from '@/stores/tableau'
import CustomModelDialog from './CustomModelDialog.vue'
import type { CustomModel } from '@/types'
import closeIconUrl from '@/assets/关闭.svg?url'

interface Props {
  open?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  open: false
})

const emit = defineEmits<{
  'update:open': [value: boolean]
  'close': []
}>()

const settingsStore = useSettingsStore()
const uiStore = useUiStore()
const tableauStore = useTableauStore()
const showAddModel = ref(false)


// ── 选项配置 ──
const THEME_OPTIONS = [
  { value: 'light' as const, label: '浅色', icon: '☀️' },
  { value: 'dark'  as const, label: '深色', icon: '🌙' },
  { value: 'auto'  as const, label: '系统', icon: '💻' },
]

const DEPTH_OPTIONS = [
  { value: 'detailed'      as const, label: '标准',  desc: '快速分析，包含主要发现' },
  { value: 'comprehensive' as const, label: '深入',  desc: '完整报告，含趋势预测' },
]

// ── 双向绑定 ──
const language = computed({
  get: () => settingsStore.language,
  set: (v) => settingsStore.setLanguage(v)
})

const analysisDepth = computed({
  get: () => settingsStore.analysisDepth,
  set: (v) => settingsStore.setAnalysisDepth(v)
})

const selectedModel = computed({
  get: () => settingsStore.selectedModel,
  set: (v) => settingsStore.setSelectedModel(v)
})

const theme = computed({
  get: () => uiStore.theme,
  set: (v) => uiStore.setTheme(v)
})

const datasourceOptions = computed(() => {
  const names = tableauStore.dataSources.map(ds => ds.name).filter(Boolean)
  return Array.from(new Set(names))
})

const selectedDatasourceValue = computed({
  get: () => settingsStore.datasourceName || '__AUTO__',
  set: (v: string) => {
    settingsStore.setDatasourceName(v === '__AUTO__' ? undefined : v)
  }
})

function handleEsc(event: KeyboardEvent) {
  if (event.key === 'Escape' && props.open) {
    handleClose()
  }
}

watch(
  () => props.open,
  (open) => {
    // 在 Tableau iframe 中不修改 body overflow，避免触发重新布局
    // document.body.style.overflow = open ? 'hidden' : ''
    if (open) {
      window.addEventListener('keydown', handleEsc)
      return
    }
    window.removeEventListener('keydown', handleEsc)
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  // document.body.style.overflow = ''
  window.removeEventListener('keydown', handleEsc)
})

// ── 操作 ──

function handleClose() {
  emit('update:open', false)
  emit('close')
}

function handleReset() {
  settingsStore.resetToDefaults()
  uiStore.setTheme('auto')
}

function handleModelSaved(model: CustomModel) {
  settingsStore.addCustomModel(model)
  showAddModel.value = false
}
</script>

<style scoped lang="scss">
@use '@/assets/styles/variables.scss' as *;
@use '@/assets/styles/mixins.scss' as *;

// ── 遮罩 ──
.settings-backdrop {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.24);
  /* 移除 backdrop-filter，在 Tableau iframe 中性能极差 */
  z-index: $z-index-modal-backdrop;
}


// ── 面板 ──
.settings-panel {
  position: absolute !important;
  top: 0 !important;
  right: 0 !important;
  bottom: 0 !important;
  left: auto !important;
  width: $settings-panel-width !important;
  max-width: 90vw !important;
  transform: none !important;

  background: linear-gradient(180deg, #ffffff 0%, #fafbfc 100%);

  border-left: 1px solid rgba(0, 0, 0, 0.08);
  box-shadow: -8px 0 32px rgba(0, 0, 0, 0.12), -2px 0 8px rgba(0, 0, 0, 0.06);
  z-index: $z-index-modal;
  display: flex;
  flex-direction: column;
  overflow: hidden;

  @include breakpoint-down(sm) {
    width: 100% !important;
    border-left: none;
  }
}

// ── 头部 ──
.settings-header {
  @include flex-between;
  height: 56px;
  padding: 0 18px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.07);
  flex-shrink: 0;
  background: rgba(255, 255, 255, 0.95);
}

.header-left {
  @include flex-align-center;
  gap: 8px;
}

.header-icon {
  color: $tableau-blue;
  flex-shrink: 0;
}

.header-title {
  font-size: 16px;
  font-weight: 700;
  letter-spacing: -0.2px;
  background: linear-gradient(135deg, $tableau-blue 0%, #0A4F8A 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.close-btn {
  @include flex-center;
  width: 38px;
  height: 38px;
  border-radius: 12px;
  border: 1px solid rgba(0, 0, 0, 0.08) !important;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(247, 248, 250, 0.96) 100%) !important;
  transition: all $transition-fast;
  flex-shrink: 0;
  cursor: pointer;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.10), inset 0 1px 0 rgba(255, 255, 255, 0.92);

  &:hover {
    background: linear-gradient(180deg, rgba(241, 247, 252, 0.98) 0%, rgba(231, 241, 249, 0.98) 100%) !important;
    border-color: rgba($tableau-blue, 0.26) !important;
    transform: translateY(-1px);
    box-shadow: 0 10px 20px rgba($tableau-blue, 0.18), inset 0 1px 0 rgba(255, 255, 255, 0.95);
  }

  &:active {
    transform: translateY(0) scale(0.96);
    box-shadow: 0 4px 10px rgba($tableau-blue, 0.14);
  }
}

.close-btn__icon {
  width: 20px;
  height: 20px;
  display: block;
  object-fit: contain;
}

// ── 内容 ──
.settings-body {
  flex: 1;
  overflow-y: auto;
  padding: 14px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;

  @include scrollbar(4px);

  @include breakpoint-down(sm) {
    padding: $spacing-md $spacing-sm;
  }
}

// ── 分组 ──
.settings-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  background: #ffffff;
  border: 1px solid rgba(0, 0, 0, 0.07);
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  /* 移除 hover transition，减少渲染压力 */
}

.section-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.7px;
}

// ── 设置项 ──
.setting-item {
  display: flex;
  flex-direction: column;
  gap: 7px;

  &:last-child {
    margin-bottom: 0;
  }
}

.setting-row-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: $spacing-md;

  @include breakpoint-down(sm) {
    grid-template-columns: 1fr;
  }
}

.setting-label {
  @include flex-align-center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
}

.label-icon {
  font-size: 15px;
  line-height: 1;
}

.setting-select {
  @include input-base;
  width: 100%;
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg width='10' height='6' viewBox='0 0 10 6' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%23999999' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 12px center;
  padding-right: 30px;
  font-size: 13px;
  border-radius: 10px;
  border: 1.5px solid rgba(0, 0, 0, 0.10);
  background-color: #f7f8fa;
  transition: all 0.18s ease;
  height: 38px;

  &:hover {
    border-color: rgba($tableau-blue, 0.35);
    background-color: #fff;
  }

  &:focus {
    outline: none;
    border-color: $tableau-blue;
    background-color: #fff;
    box-shadow: 0 0 0 3px rgba($tableau-blue, 0.10);
  }
}

.setting-hint {
  font-size: 11.5px;
  color: var(--text-tertiary);
  line-height: 1.6;
  padding: 8px 10px;
  background: rgba($tableau-orange, 0.06);
  border-radius: 8px;
  border-left: 3px solid rgba($tableau-orange, 0.45);
}

// ── 分析深度卡片 ──
.depth-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  align-items: stretch;
}

.depth-card {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 4px;
  padding: 10px 10px;
  border-radius: 10px;
  border: 1.5px solid rgba(0, 0, 0, 0.09) !important;
  cursor: pointer;
  text-align: left;
  transition: all 0.18s ease;
  background-color: #f7f8fa !important;
  min-height: 62px;


  &:hover:not(.active) {
    border-color: rgba($tableau-blue, 0.30) !important;
    background-color: rgba($tableau-blue, 0.03) !important;
  }

  &.active {
    border-color: $tableau-blue !important;
    background: linear-gradient(135deg, rgba($tableau-blue, 0.07) 0%, rgba($tableau-blue, 0.03) 100%) !important;
    box-shadow: 0 0 0 3px rgba($tableau-blue, 0.10);

    .depth-name {
      color: $tableau-blue;
    }
  }
}

.depth-name {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
  transition: color $transition-fast;
  white-space: nowrap;
}

.depth-desc {
  font-size: 11px;
  color: var(--text-tertiary);
  line-height: 1.4;
  white-space: normal;
  word-break: break-word;
}


// ── 添加模型按钮 ──
.add-model-btn {
  @include flex-align-center;
  gap: 7px;
  width: 100%;
  padding: 9px $spacing-sm;
  border-radius: 10px;
  border: 1.5px dashed rgba($tableau-blue, 0.30);
  font-size: 13px;
  color: $tableau-blue;
  background: rgba($tableau-blue, 0.03);
  cursor: pointer;
  transition: all 0.18s ease;
  font-weight: 500;

  &:hover {
    border-color: $tableau-blue;
    background-color: rgba($tableau-blue, 0.07);
    transform: translateY(-1px);
  }

  &:active {
    transform: translateY(0);
  }
}

// ── 主题按钮组 ──
.theme-group {
  @include flex-align-center;
  gap: 3px;
  background-color: #f0f1f3;
  border-radius: 10px;
  padding: 3px;
}

.theme-btn {
  @include flex-align-center;
  gap: 4px;
  padding: 5px 9px;
  border-radius: 8px;
  font-size: 11.5px;
  color: var(--text-secondary);
  transition: all $transition-fast;
  cursor: pointer;
  white-space: nowrap;

  &:hover:not(.active) {
    background-color: rgba(255, 255, 255, 0.70);
    color: var(--text-primary);
  }

  &.active {
    background-color: #ffffff;
    color: var(--text-primary);
    font-weight: 600;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.12), 0 0 0 0.5px rgba(0,0,0,0.05);
  }
}

.theme-label {
  line-height: 1;
}

// ── 底部 ──
.settings-footer {
  @include flex-between;
  height: 52px;
  padding: 0 18px;
  border-top: 1px solid rgba(0, 0, 0, 0.07);
  flex-shrink: 0;
  background: rgba(250, 251, 252, 0.95);
}

.reset-btn {
  @include flex-align-center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 8px;
  font-size: 12px;
  color: var(--text-secondary);
  transition: all $transition-fast;
  cursor: pointer;
  border: 1px solid transparent;

  &:hover {
    background-color: rgba($tableau-red, 0.07);
    border-color: rgba($tableau-red, 0.20);
    color: $tableau-red;
  }
}

.version-text {
  font-size: 11px;
  color: var(--text-tertiary);
  font-weight: 500;
}

// ── 过渡动画 ──
.backdrop-enter-active,
.backdrop-leave-active {
  transition: opacity 0.18s ease;
}

.backdrop-enter-from,
.backdrop-leave-to {
  opacity: 0;
}

// 禁用滑动动画，直接显示/隐藏
.slide-enter-active,
.slide-leave-active {
  transition: none;
}

.slide-enter-from,
.slide-leave-to {
  opacity: 0;
}

:global([data-theme='dark']) .settings-backdrop {
  background-color: rgba(0, 0, 0, 0.42);
}

:global([data-theme='dark']) .settings-panel {
  background: linear-gradient(180deg, #252525 0%, #1f1f1f 100%);
  border-left-color: rgba(255, 255, 255, 0.08);
}

:global([data-theme='dark']) .settings-header,
:global([data-theme='dark']) .settings-footer {
  background: rgba(42, 42, 42, 0.95);
  border-color: rgba(255, 255, 255, 0.08);
}

:global([data-theme='dark']) .settings-section {
  background: rgba(255, 255, 255, 0.02);
  border-color: rgba(255, 255, 255, 0.10);
}

:global([data-theme='dark']) .close-btn {
  background: linear-gradient(180deg, rgba(66, 66, 66, 0.92) 0%, rgba(45, 45, 45, 0.96) 100%) !important;
  border-color: rgba(255, 255, 255, 0.12) !important;
  box-shadow: 0 10px 22px rgba(0, 0, 0, 0.34), inset 0 1px 0 rgba(255, 255, 255, 0.06);
}

:global([data-theme='dark']) .close-btn:hover {
  background: linear-gradient(180deg, rgba(34, 68, 94, 0.98) 0%, rgba(29, 60, 86, 0.98) 100%) !important;
  border-color: rgba(93, 173, 226, 0.42) !important;
  box-shadow: 0 12px 24px rgba(9, 43, 67, 0.42), inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

:global([data-theme='dark']) .close-btn__icon {
  filter: brightness(0) invert(1);
}

:global([data-theme='dark']) .setting-select,
:global([data-theme='dark']) .depth-card {
  background-color: rgba(255, 255, 255, 0.04) !important;
  border-color: rgba(255, 255, 255, 0.12) !important;
  color: var(--text-primary);
}

:global([data-theme='dark']) .setting-select:hover,
:global([data-theme='dark']) .depth-card:hover:not(.active) {
  background-color: rgba(255, 255, 255, 0.06) !important;
  border-color: rgba(93, 173, 226, 0.30) !important;
}

:global([data-theme='dark']) .setting-select:focus,
:global([data-theme='dark']) .depth-card.active {
  border-color: rgba(93, 173, 226, 0.56) !important;
  box-shadow: 0 0 0 3px rgba(31, 119, 180, 0.18);
}

:global([data-theme='dark']) .depth-card.active {
  background: linear-gradient(135deg, rgba(31, 119, 180, 0.18) 0%, rgba(31, 119, 180, 0.08) 100%) !important;
}

:global([data-theme='dark']) .theme-group {
  background-color: rgba(255, 255, 255, 0.05);
}

:global([data-theme='dark']) .theme-btn:hover:not(.active) {
  background-color: rgba(255, 255, 255, 0.06);
}

:global([data-theme='dark']) .theme-btn.active {
  background-color: rgba(255, 255, 255, 0.10);
  color: #FFFFFF;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06), 0 6px 14px rgba(0, 0, 0, 0.20);
}

:global([data-theme='dark']) .reset-btn {
  background: rgba(255, 255, 255, 0.03);
  border-color: rgba(255, 255, 255, 0.08);
}

:global([data-theme='dark']) .reset-btn:hover {
  background-color: rgba($tableau-red, 0.14);
  border-color: rgba($tableau-red, 0.32);
}

</style>
