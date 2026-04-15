<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { workflowApi } from '@/api'
import { message } from 'ant-design-vue'
import type { Workflow, WorkflowTemplate } from '@/types'

const workflows = ref<Workflow[]>([])
const templates = ref<WorkflowTemplate[]>([])
const loading = ref(false)

const workflowColumns = [
  { title: 'Name', dataIndex: 'name', key: 'name', width: 150 },
  { title: 'Status', dataIndex: 'status', key: 'status', width: 100 },
  { title: 'Template', dataIndex: 'template_id', key: 'template_id', width: 150 },
  { title: 'Steps', key: 'steps', width: 100 },
]

onMounted(async () => {
  await fetchWorkflows()
})

async function fetchWorkflows() {
  loading.value = true
  try {
    const [workflowsData, templatesData] = await Promise.all([
      workflowApi.list(),
      workflowApi.getTemplates(),
    ])

    workflows.value = workflowsData.workflows
    templates.value = templatesData.templates
  } catch (error) {
    message.error('Failed to load workflows')
  } finally {
    loading.value = false
  }
}

async function handleCreateFromTemplate(template: WorkflowTemplate) {
  try {
    await workflowApi.create({ template_id: template.id })
    message.success(`Workflow created from template: ${template.name}`)
    await fetchWorkflows()
  } catch (error) {
    message.error('Failed to create workflow')
  }
}
</script>

<template>
  <div>
    <!-- Active Workflows Section -->
    <div style="margin-bottom: 32px">
      <h2>Active Workflows</h2>
      <a-table
        :columns="workflowColumns"
        :data-source="workflows"
        :loading="loading"
        :pagination="{ pageSize: 10 }"
        :scroll="{ x: 500 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'status'">
            <a-tag :color="record.status === 'active' ? 'success' : 'default'">
              {{ record.status }}
            </a-tag>
          </template>
          <template v-if="column.key === 'steps'">
            {{ record.steps?.length || 0 }}
          </template>
        </template>
      </a-table>
    </div>

    <!-- Workflow Templates Section -->
    <div>
      <h2>Workflow Templates</h2>
      <a-row :gutter="[16, 16]">
        <a-col
          v-for="template in templates"
          :key="template.id"
          :xs="24"
          :sm="12"
          :lg="8"
        >
          <a-card :bordered="false">
            <template #title>
              {{ template.name }}
            </template>
            <div style="margin-bottom: 12px">
              <p style="color: #94a3b8; margin: 0 0 8px 0">{{ template.description }}</p>
              <a-tag>{{ template.category }}</a-tag>
            </div>
            <div style="color: #64748b; font-size: 12px; margin-bottom: 16px">
              Steps: {{ template.steps?.length || 0 }}
            </div>
            <a-button
              type="primary"
              block
              @click="handleCreateFromTemplate(template)"
            >
              Create from Template
            </a-button>
          </a-card>
        </a-col>
      </a-row>
    </div>
  </div>
</template>
