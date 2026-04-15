<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { providerApi } from '@/api'
import { message } from 'ant-design-vue'
import type { Provider } from '@/types'

const providers = ref<Provider[]>([])
const loading = ref(false)
const addModalVisible = ref(false)
const addForm = ref({
  name: '',
  type: 'openai',
  base_url: '',
})

const columns = [
  { title: 'Name', dataIndex: 'name', key: 'name', width: 150 },
  { title: 'Type', dataIndex: 'type', key: 'type', width: 100 },
  { title: 'Base URL', dataIndex: 'base_url', key: 'base_url', width: 200 },
  { title: 'Models', key: 'models', width: 100 },
  { title: 'Status', dataIndex: 'status', key: 'status', width: 100 },
  { title: 'Actions', key: 'actions', width: 150 },
]

onMounted(async () => {
  await fetchProviders()
})

async function fetchProviders() {
  loading.value = true
  try {
    const response = await providerApi.list()
    providers.value = response.providers
  } catch (error) {
    message.error('Failed to load providers')
  } finally {
    loading.value = false
  }
}

async function handleAddProvider() {
  if (!addForm.value.name || !addForm.value.base_url) {
    message.error('Please fill in all required fields')
    return
  }

  try {
    await providerApi.register(addForm.value)
    message.success('Provider added successfully')
    addModalVisible.value = false
    addForm.value = { name: '', type: 'openai', base_url: '' }
    await fetchProviders()
  } catch (error) {
    message.error('Failed to add provider')
  }
}

async function handleDetectModels(provider: Provider) {
  try {
    await providerApi.detectModels(provider.id)
    message.success('Models detected successfully')
    await fetchProviders()
  } catch (error) {
    message.error('Failed to detect models')
  }
}
</script>

<template>
  <div>
    <div style="margin-bottom: 16px">
      <a-button type="primary" @click="addModalVisible = true">
        Add Provider
      </a-button>
    </div>

    <a-table
      :columns="columns"
      :data-source="providers"
      :loading="loading"
      :pagination="{ pageSize: 10 }"
      :scroll="{ x: 800 }"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'models'">
          {{ record.models?.length || 0 }}
        </template>
        <template v-if="column.key === 'status'">
          <a-tag :color="record.status === 'active' ? 'success' : 'default'">
            {{ record.status }}
          </a-tag>
        </template>
        <template v-if="column.key === 'actions'">
          <a-space>
            <a-button
              type="link"
              size="small"
              @click="handleDetectModels(record)"
            >
              Detect
            </a-button>
            <a-button type="link" size="small">
              Edit
            </a-button>
          </a-space>
        </template>
      </template>
    </a-table>

    <!-- Add Provider Modal -->
    <a-modal
      v-model:visible="addModalVisible"
      title="Add New Provider"
      @ok="handleAddProvider"
    >
      <a-form style="margin-top: 16px">
        <a-form-item label="Provider Name">
          <a-input v-model:value="addForm.name" placeholder="e.g., OpenAI" />
        </a-form-item>
        <a-form-item label="Type">
          <a-select v-model:value="addForm.type">
            <a-select-option value="openai">OpenAI</a-select-option>
            <a-select-option value="anthropic">Anthropic</a-select-option>
            <a-select-option value="other">Other</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="Base URL">
          <a-input v-model:value="addForm.base_url" placeholder="https://api.example.com" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>
