<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { projectApi } from '@/api'
import { message } from 'ant-design-vue'
import type { Project } from '@/types'

const router = useRouter()
const projects = ref<Project[]>([])
const loading = ref(false)
const createModalVisible = ref(false)
const createForm = ref({
  name: '',
  description: '',
})

const columns = [
  { title: 'Name', dataIndex: 'name', key: 'name', width: 150 },
  { title: 'Status', dataIndex: 'status', key: 'status', width: 100 },
  { title: 'Members', key: 'members', width: 100 },
  { title: 'Tasks', key: 'tasks', width: 100 },
  { title: 'Created', dataIndex: 'created_at', key: 'created_at', width: 150 },
]

onMounted(async () => {
  await fetchProjects()
})

async function fetchProjects() {
  loading.value = true
  try {
    const response = await projectApi.list()
    projects.value = response.projects
  } catch (error) {
    message.error('Failed to load projects')
  } finally {
    loading.value = false
  }
}

async function handleCreateProject() {
  if (!createForm.value.name) {
    message.error('Please enter project name')
    return
  }

  try {
    await projectApi.create(createForm.value)
    message.success('Project created successfully')
    createModalVisible.value = false
    createForm.value = { name: '', description: '' }
    await fetchProjects()
  } catch (error) {
    message.error('Failed to create project')
  }
}

function handleRowClick(record: Project) {
  router.push({ name: 'ProjectDetail', params: { id: record.id } })
}
</script>

<template>
  <div>
    <div style="margin-bottom: 16px">
      <a-button type="primary" @click="createModalVisible = true">
        Create Project
      </a-button>
    </div>

    <a-table
      :columns="columns"
      :data-source="projects"
      :loading="loading"
      :pagination="{ pageSize: 10 }"
      :scroll="{ x: 600 }"
      @row="(record) => handleRowClick(record)"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'status'">
          <a-tag :color="record.status === 'active' ? 'success' : 'default'">
            {{ record.status }}
          </a-tag>
        </template>
        <template v-if="column.key === 'members'">
          {{ record.members.length }}
        </template>
        <template v-if="column.key === 'tasks'">
          {{ record.tasks?.length || 0 }}
        </template>
      </template>
    </a-table>

    <!-- Create Modal -->
    <a-modal
      v-model:visible="createModalVisible"
      title="Create New Project"
      @ok="handleCreateProject"
    >
      <a-form style="margin-top: 16px">
        <a-form-item label="Project Name">
          <a-input v-model:value="createForm.name" placeholder="Enter project name" />
        </a-form-item>
        <a-form-item label="Description">
          <a-textarea
            v-model:value="createForm.description"
            placeholder="Enter project description"
            :rows="4"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>
