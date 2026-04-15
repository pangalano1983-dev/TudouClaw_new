<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAgentStore } from '@/stores/agents'
import { agentApi } from '@/api'
import { message } from 'ant-design-vue'
import type { Agent } from '@/types'

const router = useRouter()
const agentStore = useAgentStore()
const loading = ref(false)
const roleFilter = ref<string | undefined>(undefined)
const statusFilter = ref<string | undefined>(undefined)

const roles = computed(() => {
  const set = new Set(agentStore.agents.map((a) => a.role))
  return Array.from(set)
})

const statuses = ['idle', 'busy', 'error', 'offline']

const filteredAgents = computed(() => {
  return agentStore.agents.filter((agent) => {
    if (roleFilter.value && agent.role !== roleFilter.value) return false
    if (statusFilter.value && agent.status !== statusFilter.value) return false
    return true
  })
})

const columns = [
  { title: 'Name', dataIndex: 'name', key: 'name', width: 150 },
  { title: 'Role', dataIndex: 'role', key: 'role', width: 120 },
  { title: 'Status', dataIndex: 'status', key: 'status', width: 100 },
  { title: 'Model', dataIndex: 'model', key: 'model', width: 150 },
  { title: 'Node', dataIndex: 'node_id', key: 'node_id', width: 120 },
  { title: 'Actions', key: 'actions', width: 200 },
]

onMounted(async () => {
  await fetchAgents()
})

async function fetchAgents() {
  loading.value = true
  try {
    await agentStore.fetchAgents()
  } catch (error) {
    message.error('Failed to load agents')
  } finally {
    loading.value = false
  }
}

async function handleWake(agent: Agent) {
  try {
    await agentApi.wake(agent.id)
    message.success(`Agent ${agent.name} waked up`)
    await fetchAgents()
  } catch (error) {
    message.error('Failed to wake agent')
  }
}

async function handleClear(agent: Agent) {
  try {
    await agentApi.clear(agent.id)
    message.success(`Agent ${agent.name} cleared`)
    await fetchAgents()
  } catch (error) {
    message.error('Failed to clear agent')
  }
}

function handleChat(id: string) {
  router.push({ name: 'AgentChat', params: { id } })
}
</script>

<template>
  <div>
    <!-- Filters -->
    <a-row :gutter="[16, 16]" style="margin-bottom: 16px">
      <a-col :xs="24" :sm="12" :lg="8">
        <a-select
          v-model:value="roleFilter"
          placeholder="Filter by role"
          allow-clear
          style="width: 100%"
        >
          <a-select-option v-for="role in roles" :key="role" :value="role">
            {{ role }}
          </a-select-option>
        </a-select>
      </a-col>
      <a-col :xs="24" :sm="12" :lg="8">
        <a-select
          v-model:value="statusFilter"
          placeholder="Filter by status"
          allow-clear
          style="width: 100%"
        >
          <a-select-option v-for="status in statuses" :key="status" :value="status">
            {{ status }}
          </a-select-option>
        </a-select>
      </a-col>
    </a-row>

    <!-- Table -->
    <a-table
      :columns="columns"
      :data-source="filteredAgents"
      :loading="loading"
      :pagination="{ pageSize: 10 }"
      :scroll="{ x: 800 }"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'status'">
          <a-tag
            :color="
              record.status === 'idle'
                ? 'success'
                : record.status === 'busy'
                  ? 'processing'
                  : 'error'
            "
          >
            {{ record.status }}
          </a-tag>
        </template>
        <template v-if="column.key === 'actions'">
          <a-space>
            <a-button
              type="link"
              size="small"
              @click="handleChat(record.id)"
            >
              Chat
            </a-button>
            <a-button
              type="link"
              size="small"
              @click="handleWake(record)"
            >
              Wake
            </a-button>
            <a-button
              type="link"
              size="small"
              danger
              @click="handleClear(record)"
            >
              Clear
            </a-button>
          </a-space>
        </template>
      </template>
    </a-table>
  </div>
</template>
