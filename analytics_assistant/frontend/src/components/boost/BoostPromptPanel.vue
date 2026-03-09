<!-- Boost Prompt 面板组件 -->
<template>
  <div class="boost-prompt-panel">
    <div class="panel-header">
      <h3>{{ t('boost.title') }}</h3>
      <el-button
        text
        :icon="CloseIcon"
        @click="emit('close')"
        :aria-label="t('common.close')"
      />
    </div>

    <div class="panel-content">
      <!-- 内置快捷提示 -->
      <div class="prompt-section">
        <h4>{{ t('boost.builtIn') }}</h4>
        <div class="prompt-grid">
          <BoostPromptCard
            v-for="prompt in builtInPrompts"
            :key="prompt.id"
            :prompt="prompt"
            @click="handleSelectPrompt(prompt)"
          />
        </div>
      </div>

      <!-- 自定义快捷提示 -->
      <div v-if="customPrompts.length > 0" class="prompt-section">
        <div class="section-header">
          <h4>{{ t('boost.custom') }}</h4>
          <el-button
            text
            :icon="PlusIcon"
            @click="handleAddCustomPrompt"
          >
            {{ t('boost.add') }}
          </el-button>
        </div>
        <div class="prompt-grid">
          <BoostPromptCard
            v-for="prompt in customPrompts"
            :key="prompt.id"
            :prompt="prompt"
            :editable="true"
            @click="handleSelectPrompt(prompt)"
            @edit="handleEditPrompt(prompt)"
            @delete="handleDeletePrompt(prompt.id)"
          />
        </div>
      </div>

      <!-- 添加自定义提示按钮 -->
      <el-button
        v-else
        class="add-custom-button"
        :icon="PlusIcon"
        @click="handleAddCustomPrompt"
      >
        {{ t('boost.addCustom') }}
      </el-button>
    </div>

    <!-- 添加/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEditing ? t('boost.edit') : t('boost.add')"
      width="500px"
    >
      <el-form :model="formData" label-width="80px">
        <el-form-item :label="t('boost.title')">
          <el-input
            v-model="formData.title"
            :placeholder="t('boost.titlePlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('boost.content')">
          <el-input
            v-model="formData.content"
            type="textarea"
            :rows="4"
            :placeholder="t('boost.contentPlaceholder')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">
          {{ t('common.cancel') }}
        </el-button>
        <el-button type="primary" @click="handleSaveCustomPrompt">
          {{ t('common.save') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Close as CloseIcon, Plus as PlusIcon } from '@element-plus/icons-vue'
import BoostPromptCard from './BoostPromptCard.vue'
import type { BoostPrompt } from '@/types'
import { BUILT_IN_PROMPTS } from '@/types/boost'
import { boostPromptStorage } from '@/utils/storage'
import { generateId } from '@/utils/id'

interface Emits {
  (e: 'select', text: string): void
  (e: 'close'): void
}

const emit = defineEmits<Emits>()
const { t } = useI18n()

// 状态
const customPrompts = ref<BoostPrompt[]>(boostPromptStorage.getAll())
const dialogVisible = ref(false)
const isEditing = ref(false)
const formData = ref({
  id: '',
  title: '',
  content: ''
})

// 计算属性
const builtInPrompts = computed(() => BUILT_IN_PROMPTS)

// 选择快捷提示
const handleSelectPrompt = (prompt: BoostPrompt) => {
  emit('select', prompt.content)
}

// 添加自定义快捷提示
const handleAddCustomPrompt = () => {
  isEditing.value = false
  formData.value = {
    id: '',
    title: '',
    content: ''
  }
  dialogVisible.value = true
}

// 编辑快捷提示
const handleEditPrompt = (prompt: BoostPrompt) => {
  isEditing.value = true
  formData.value = {
    id: prompt.id,
    title: prompt.title,
    content: prompt.content
  }
  dialogVisible.value = true
}

// 保存自定义快捷提示
const handleSaveCustomPrompt = () => {
  if (!formData.value.title.trim() || !formData.value.content.trim()) {
    ElMessage.warning(t('boost.fillRequired'))
    return
  }

  if (isEditing.value) {
    // 更新
    boostPromptStorage.update(formData.value.id, {
      title: formData.value.title,
      content: formData.value.content
    })
    ElMessage.success(t('boost.updateSuccess'))
  } else {
    // 新增
    const newPrompt: BoostPrompt = {
      id: generateId(),
      title: formData.value.title,
      content: formData.value.content,
      category: 'custom' as any,
      isBuiltIn: false
    }
    boostPromptStorage.add(newPrompt)
    ElMessage.success(t('boost.addSuccess'))
  }

  // 刷新列表
  customPrompts.value = boostPromptStorage.getAll()
  dialogVisible.value = false
}

// 删除快捷提示
const handleDeletePrompt = async (id: string) => {
  try {
    await ElMessageBox.confirm(
      t('boost.deleteConfirm'),
      t('common.warning'),
      {
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
        type: 'warning'
      }
    )

    boostPromptStorage.remove(id)
    customPrompts.value = boostPromptStorage.getAll()
    ElMessage.success(t('boost.deleteSuccess'))
  } catch {
    // 用户取消
  }
}
</script>

<style scoped>
.boost-prompt-panel {
  position: absolute;
  bottom: 100%;
  left: 0;
  right: 0;
  max-height: 400px;
  background-color: var(--header-bg);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
}

.panel-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.panel-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.prompt-section {
  margin-bottom: 24px;
}

.prompt-section:last-child {
  margin-bottom: 0;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.prompt-section h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-secondary);
}

.prompt-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}

.add-custom-button {
  width: 100%;
}

/* 滚动条样式 */
.panel-content::-webkit-scrollbar {
  width: 6px;
}

.panel-content::-webkit-scrollbar-track {
  background: var(--scrollbar-track);
}

.panel-content::-webkit-scrollbar-thumb {
  background: var(--scrollbar-thumb);
  border-radius: 3px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .boost-prompt-panel {
    max-height: 300px;
  }

  .prompt-grid {
    grid-template-columns: 1fr;
  }
}
</style>
