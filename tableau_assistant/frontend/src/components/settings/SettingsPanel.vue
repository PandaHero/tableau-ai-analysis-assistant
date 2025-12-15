<template>
  <el-drawer
    :model-value="visible"
    :title="t('settings.title')"
    direction="rtl"
    :size="panelWidth"
    @close="$emit('close')"
  >
    <div class="settings-content">
      <!-- 数据源选择 -->
      <div class="setting-section">
        <h4 class="section-title">{{ t('settings.datasource') }}</h4>
        <el-select
          v-model="currentDatasource"
          :placeholder="t('settings.datasource.placeholder')"
          class="full-width"
          :teleported="false"
          @change="handleDatasourceChange"
        >
          <el-option
            v-for="ds in dataSources"
            :key="ds.name"
            :label="ds.name"
            :value="ds.name"
          />
        </el-select>
      </div>

      <!-- 语言设置 -->
      <div class="setting-section">
        <h4 class="section-title">{{ t('settings.language') }}</h4>
        <el-radio-group v-model="language" @change="handleLanguageChange">
          <el-radio-button value="zh">{{ t('settings.language.zh') }}</el-radio-button>
          <el-radio-button value="en">{{ t('settings.language.en') }}</el-radio-button>
        </el-radio-group>
      </div>

      <!-- 分析深度 -->
      <div class="setting-section">
        <h4 class="section-title">{{ t('settings.analysisDepth') }}</h4>
        <el-radio-group v-model="analysisDepth" @change="handleDepthChange">
          <el-radio value="detailed">
            <span class="radio-label">{{ t('settings.analysisDepth.detailed') }}</span>
            <span class="radio-desc">{{ language === 'zh' ? '标准分析，包含数据支撑和主要发现' : 'Standard analysis with data support and key findings' }}</span>
          </el-radio>
          <el-radio value="comprehensive">
            <span class="radio-label">{{ t('settings.analysisDepth.comprehensive') }}</span>
            <span class="radio-desc">{{ language === 'zh' ? '完整报告，包含趋势预测和行动建议' : 'Full report with trend predictions and action recommendations' }}</span>
          </el-radio>
        </el-radio-group>
      </div>

      <!-- AI 模型选择 -->
      <div class="setting-section">
        <h4 class="section-title">{{ t('settings.model') }}</h4>
        <el-select
          v-model="selectedModel"
          :placeholder="t('settings.model')"
          class="full-width"
          :teleported="false"
          @change="handleModelChange"
        >
          <el-option-group :label="t('settings.model.builtin')">
            <el-option
              v-for="model in builtinModels"
              :key="model.id"
              :label="model.name"
              :value="model.id"
            >
              <span>{{ model.name }}</span>
              <span class="model-desc">{{ model.description }}</span>
            </el-option>
          </el-option-group>
          <el-option-group v-if="customModels.length" :label="t('settings.model.custom')">
            <el-option
              v-for="model in customModels"
              :key="`custom_${model.name}`"
              :label="model.name"
              :value="`custom_${model.name}`"
            >
              {{ model.name }}
            </el-option>
          </el-option-group>
        </el-select>
        <el-button 
          type="primary" 
          link 
          class="add-model-btn"
          @click="showCustomModelDialog = true"
        >
          + {{ t('settings.model.add') }}
        </el-button>
      </div>

      <!-- 主题设置 -->
      <div class="setting-section">
        <h4 class="section-title">{{ t('settings.theme') }}</h4>
        <el-radio-group v-model="theme" @change="handleThemeChange">
          <el-radio-button value="light">{{ t('settings.theme.light') }}</el-radio-button>
          <el-radio-button value="dark">{{ t('settings.theme.dark') }}</el-radio-button>
          <el-radio-button value="system">{{ t('settings.theme.system') }}</el-radio-button>
        </el-radio-group>
      </div>

      <!-- 清除历史 -->
      <div class="setting-section danger-zone">
        <h4 class="section-title">{{ language === 'zh' ? '危险操作' : 'Danger Zone' }}</h4>
        <el-button type="danger" plain @click="handleClearHistory">
          {{ language === 'zh' ? '清除所有历史' : 'Clear All History' }}
        </el-button>
      </div>
    </div>

    <!-- 自定义模型对话框 -->
    <CustomModelDialog
      v-model:visible="showCustomModelDialog"
      @save="handleSaveCustomModel"
    />
  </el-drawer>
</template>

<script setup lang="ts">
/**
 * SettingsPanel 组件
 * 设置面板
 * Requirements: 新增设置功能
 */
import { ref, computed, watch } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { useSettingsStore } from '@/stores/settings'
import { useSessionStore } from '@/stores/session'
import { useUiStore } from '@/stores/ui'
import { useTableauStore } from '@/stores/tableau'
import { useI18n } from '@/utils/i18n'
import { BUILTIN_MODELS } from '@/types'
import type { CustomModel, Language, AnalysisDepth, Theme } from '@/types'
import CustomModelDialog from './CustomModelDialog.vue'

defineProps<{
  visible: boolean
}>()

defineEmits<{
  close: []
}>()

const settingsStore = useSettingsStore()
const sessionStore = useSessionStore()
const uiStore = useUiStore()
const tableauStore = useTableauStore()
const { t } = useI18n()

// 响应式宽度
const panelWidth = computed(() => 
  uiStore.windowWidth < 480 ? '100%' : '320px'
)

// 数据源列表
const dataSources = computed(() => tableauStore.dataSources || [])

// 模型列表
const builtinModels = BUILTIN_MODELS
const customModels = computed(() => settingsStore.customModels)

// 本地状态（双向绑定）
const language = ref<Language>(settingsStore.language)
const analysisDepth = ref<AnalysisDepth>(settingsStore.analysisDepth)
const selectedModel = ref<string>(settingsStore.selectedModel)
const theme = ref<Theme>(uiStore.theme)

// 监听 store 变化，同步本地状态
watch(() => settingsStore.language, (val) => { language.value = val })

// 数据源：优先使用 settingsStore 的值，否则使用第一个数据源
const currentDatasource = computed({
  get: () => {
    if (settingsStore.datasourceName) {
      return settingsStore.datasourceName
    }
    // 默认选择第一个数据源
    if (dataSources.value.length > 0) {
      return dataSources.value[0].name
    }
    return ''
  },
  set: (val: string) => {
    settingsStore.setDatasourceName(val)
  }
})

const showCustomModelDialog = ref(false)

// 事件处理
function handleDatasourceChange(name: string) {
  settingsStore.setDatasourceName(name)
}

function handleLanguageChange(lang: Language) {
  settingsStore.setLanguage(lang)
}

function handleDepthChange(depth: AnalysisDepth) {
  settingsStore.setAnalysisDepth(depth)
}

function handleModelChange(modelId: string) {
  settingsStore.setSelectedModel(modelId)
}

function handleThemeChange(newTheme: Theme) {
  uiStore.setTheme(newTheme)
}

async function handleClearHistory() {
  try {
    await ElMessageBox.confirm(
      '确定要清除所有对话历史吗？此操作不可恢复。',
      '确认清除',
      { type: 'warning' }
    )
    sessionStore.clearAllSessions()
    ElMessage.success('历史已清除')
  } catch {
    // 用户取消
  }
}

function handleSaveCustomModel(model: CustomModel) {
  settingsStore.addCustomModel(model)
  showCustomModelDialog.value = false
  ElMessage.success('模型已添加')
}
</script>

<style scoped>
.settings-content {
  padding: 0 4px;
}

.setting-section {
  margin-bottom: 24px;
}

.section-title {
  margin: 0 0 12px 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
}

.full-width {
  width: 100%;
}

.radio-label {
  font-weight: 500;
  color: var(--color-text);
}

.radio-desc {
  display: block;
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-top: 2px;
}

.model-desc {
  margin-left: 8px;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.add-model-btn {
  margin-top: 8px;
  padding: 0;
}

.danger-zone {
  padding-top: 16px;
  border-top: 1px solid var(--color-border);
}

:deep(.el-radio) {
  display: flex;
  align-items: flex-start;
  margin-bottom: 12px;
}

:deep(.el-radio__label) {
  display: flex;
  flex-direction: column;
}
</style>
