<template>
  <div class="header-bar-content">
    <!-- 首页状态：Logo + 标题 -->
    <div v-if="!isChat" class="header-left">
      <div class="logo">
        <img src="@/assets/tableau_logo.svg" alt="Tableau" width="28" height="28" />
      </div>
      <span class="title">{{ t('app.title') }}</span>
    </div>

    <!-- 对话页面状态：返回按钮 -->
    <div v-else class="header-left">
      <el-button 
        :icon="ArrowLeft" 
        text 
        @click="handleBack"
        class="back-button"
      >
        {{ t('header.back') }}
      </el-button>
    </div>

    <!-- 右侧：设置按钮 -->
    <div class="header-right">
      <el-button 
        :icon="Setting" 
        circle 
        text
        @click="handleSettings"
        class="settings-button"
        :title="t('header.settings')"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ArrowLeft, Setting } from '@element-plus/icons-vue'
import { useI18n } from '@/utils/i18n'

const { t } = useI18n()

defineProps<{
  isChat: boolean
}>()

const emit = defineEmits<{
  back: []
  settings: []
}>()

function handleBack() {
  emit('back')
}

function handleSettings() {
  emit('settings')
}
</script>

<style scoped>
.header-bar-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 100%;
  padding: 0 16px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo {
  display: flex;
  align-items: center;
}

.logo img {
  display: block;
}

.title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text);
  white-space: nowrap;
}

.back-button {
  font-size: 13px;
  color: var(--color-text-secondary);
  padding: 4px 12px;
  height: 28px;
  border-radius: 14px;
  background-color: var(--btn-bg, #f7f8fa);
  border: 1px solid var(--color-border);
  transition: all 0.2s ease;
}

.back-button:hover {
  background-color: var(--btn-bg-hover, #edf2f7);
  color: var(--tableau-blue);
  border-color: var(--tableau-blue);
}

.settings-button {
  width: 28px;
  height: 28px;
  color: var(--color-text-secondary);
  background-color: var(--btn-bg, #f7f8fa);
  border: 1px solid var(--color-border);
  transition: all 0.2s ease;
}

.settings-button:hover {
  color: var(--tableau-blue);
  background-color: var(--btn-bg-hover);
  border-color: var(--tableau-blue);
}
</style>
