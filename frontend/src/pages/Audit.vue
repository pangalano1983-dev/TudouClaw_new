<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { configApi } from '@/api'
import { message } from 'ant-design-vue'

const auditLogs = ref<any[]>([])
const loading = ref(false)
const actionFilter = ref<string | undefined>(undefined)

const actions = [
  'create',
  'update',
  'delete',
  'login',
  'logout',
  'enable',
  'disable',
]

const columns = [
  { title: 'Timestamp', dataIndex: 'timestamp', key: 'timestamp', width: 180 },
  { title: 'Action', dataIndex: 'action', key: 'action', width: 100 },
  { title: 'User', dataIndex: 'user', key: 'user', width: 120 },
  { title: 'Details', dataIndex: 'details', key: 'details', width: 250 },
]

onMounted(async () => {
  await fetchAuditLogs()
})

async function fetchAuditLogs() {
  loading.value = true
  try {
    const response = await configApi.getAudit()
    auditLogs.value = response.audit_logs || []
  } catch (error) {
    message.error('Failed to load audit logs')
  } finally {
    loading.value = false
  }
}

const filteredLogs = computed(() => {
  if (!actionFilter.value) return auditLogs.value
  return auditLogs.value.filter((log) => log.action === actionFilter.value)
})

import { computed } from 'vue'
</script>

<template>
  <div>
    <!-- Filters -->
    <div style="margin-bottom: 16px">
      <a-select
        v-model:value="actionFilter"
        placeholder="Filter by action"
        allow-clear
        style="width: 200px"
      >
        <a-select-option v-for="action in actions" :key="action" :value="action">
          {{ action }}
        </a-select-option>
      </a-select>
    </div>

    <!-- Audit Table -->
    <a-table
      :columns="columns"
      :data-source="filteredLogs"
      :loading="loading"
      :pagination="{ pageSize: 20 }"
      :scroll="{ x: 650 }"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'action'">
          <a-tag
            :color="
              record.action === 'create' || record.action === 'enable'
                ? 'success'
                : record.action === 'delete' || record.action === 'disable'
                  ? 'error'
                  : 'default'
            "
          >
            {{ record.action }}
          </a-tag>
        </template>
        <template v-if="column.key === 'details'">
          <span style="color: #94a3b8; font-size: 12px">
            {{ record.details || '-' }}
          </span>
        </template>
      </template>
    </a-table>
  </div>
</template>
