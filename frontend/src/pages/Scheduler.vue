<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { schedulerApi } from '@/api'
import { message } from 'ant-design-vue'

const jobs = ref<any[]>([])
const loading = ref(false)

const columns = [
  { title: 'Name', dataIndex: 'name', key: 'name', width: 150 },
  { title: 'Schedule', dataIndex: 'schedule', key: 'schedule', width: 150 },
  { title: 'Status', dataIndex: 'status', key: 'status', width: 100 },
  { title: 'Last Run', dataIndex: 'last_run', key: 'last_run', width: 180 },
  { title: 'Next Run', dataIndex: 'next_run', key: 'next_run', width: 180 },
  { title: 'Actions', key: 'actions', width: 150 },
]

onMounted(async () => {
  await fetchJobs()
})

async function fetchJobs() {
  loading.value = true
  try {
    const response = await schedulerApi.listJobs()
    jobs.value = response.jobs || []
  } catch (error) {
    message.error('Failed to load jobs')
  } finally {
    loading.value = false
  }
}

async function handleRunNow(job: any) {
  try {
    await schedulerApi.manageJob({ action: 'run', job_id: job.id })
    message.success(`Job ${job.name} triggered`)
    await fetchJobs()
  } catch (error) {
    message.error('Failed to run job')
  }
}

async function handleDeleteJob(job: any) {
  try {
    await schedulerApi.manageJob({ action: 'delete', job_id: job.id })
    message.success(`Job ${job.name} deleted`)
    await fetchJobs()
  } catch (error) {
    message.error('Failed to delete job')
  }
}
</script>

<template>
  <div>
    <a-table
      :columns="columns"
      :data-source="jobs"
      :loading="loading"
      :pagination="{ pageSize: 10 }"
      :scroll="{ x: 900 }"
    >
      <template #bodyCell="{ column, record }">
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
              @click="handleRunNow(record)"
            >
              Run Now
            </a-button>
            <a-button type="link" size="small">
              Edit
            </a-button>
            <a-button
              type="link"
              size="small"
              danger
              @click="handleDeleteJob(record)"
            >
              Delete
            </a-button>
          </a-space>
        </template>
      </template>
    </a-table>
  </div>
</template>
