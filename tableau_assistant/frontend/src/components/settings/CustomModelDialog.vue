<template>
  <el-dialog
    :model-value="visible"
    title="添加自定义模型"
    width="400px"
    @close="$emit('update:visible', false)"
  >
    <el-form :model="form" :rules="rules" ref="formRef" label-position="top">
      <el-form-item label="模型名称" prop="name">
        <el-input v-model="form.name" placeholder="例如：My GPT" />
      </el-form-item>
      
      <el-form-item label="API 地址" prop="apiBase">
        <el-input v-model="form.apiBase" placeholder="https://api.example.com/v1" />
      </el-form-item>
      
      <el-form-item label="API Key">
        <el-input 
          v-model="form.apiKey" 
          type="password" 
          placeholder="可选"
          show-password
        />
      </el-form-item>
      
      <el-form-item label="模型标识">
        <el-input v-model="form.modelId" placeholder="例如：gpt-4（可选）" />
      </el-form-item>
    </el-form>
    
    <template #footer>
      <div class="dialog-footer">
        <el-button @click="$emit('update:visible', false)">取消</el-button>
        <el-button 
          type="info" 
          :loading="testing"
          @click="testConnection"
        >
          测试连接
        </el-button>
        <el-button type="primary" @click="handleSave">保存</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * CustomModelDialog 组件
 * 自定义模型配置对话框
 * Requirements: 新增设置功能
 */
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { useSettingsStore } from '@/stores/settings'
import type { CustomModel } from '@/types'

defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  save: [model: CustomModel]
}>()

const settingsStore = useSettingsStore()
const formRef = ref<FormInstance>()
const testing = ref(false)

const form = reactive({
  name: '',
  apiBase: '',
  apiKey: '',
  modelId: ''
})

const rules: FormRules = {
  name: [{ required: true, message: '请输入模型名称', trigger: 'blur' }],
  apiBase: [
    { required: true, message: '请输入 API 地址', trigger: 'blur' },
    { type: 'url', message: '请输入有效的 URL', trigger: 'blur' }
  ]
}

async function testConnection() {
  testing.value = true
  try {
    const success = await settingsStore.testCustomModel({
      name: form.name,
      apiBase: form.apiBase,
      apiKey: form.apiKey,
      modelId: form.modelId
    })
    if (success) {
      ElMessage.success('连接成功')
    } else {
      ElMessage.error('连接失败')
    }
  } catch {
    ElMessage.error('测试失败')
  } finally {
    testing.value = false
  }
}

async function handleSave() {
  if (!formRef.value) return
  
  try {
    await formRef.value.validate()
    emit('save', {
      name: form.name,
      apiBase: form.apiBase,
      apiKey: form.apiKey || undefined,
      modelId: form.modelId || undefined
    })
    // 重置表单
    formRef.value.resetFields()
  } catch {
    // 验证失败
  }
}
</script>

<style scoped>
.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
