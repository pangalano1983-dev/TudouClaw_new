<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { nodeApi } from '@/api'
import { message } from 'ant-design-vue'
import type { ClusterNode } from '@/types'

const nodes = ref<ClusterNode[]>([])
const loading = ref(false)
const selectedNode = ref<ClusterNode | null>(null)
const nodeConfig = ref<Record<string, any>>({})

const columns = [
  { title: 'Name', dataIndex: 'name', key: 'name', width: 150 },
  { title: 'Status', dataIndex: 'status', key: 'status', width: 100 },
  { title: 'Address', dataIndex: 'address', key: 'address', width: 180 },
  { title: 'Agents', dataIndex: 'agent_count', key: 'agent_count', width: 80 },
]

onMounted(async () => {
  await fetchNodes()
})

async function fetchNodes() {
  loading.value = true
  try {
    const response = await nodeApi.list()
    nodes.value = response.nodes
  } catch (error) {
    message.error('Failed to load nodes')
  } finally {
    loading.value = false
  }
}

async function handleSelectNode(node: ClusterNode) {
  selectedNode.value = node
  try {
    const config = await nodeApi.getConfig(node.id)
    nodeConfig.value = config
  } catch (error) {
    message.error('Failed to load node config')
  }
}

async function handleSaveConfig() {
  if (!selectedNode.value) return

  try {
    await nodeApi.updateConfig(selectedNode.value.id, nodeConfig.value)
    message.success('Node config updated')
  } catch (error) {
    message.error('Failed to update config')
  }
}

async function handleSyncConfig() {
  if (!selectedNode.value) return

  try {
    await nodeApi.syncConfig(selectedNode.value.id)
    message.success('Node config synced')
  } catch (error) {
    message.error('Failed to sync config')
  }
}
</script>

<template>
  <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px">
    <!-- Nodes Table -->
    <div>
      <a-table
        :columns="columns"
        :data-source="nodes"
        :loading="loading"
        :pagination="false"
        @row="(record) => handleSelectNode(record)"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'status'">
            <a-tag :color="record.status === 'online' ? 'success' : 'error'">
              {{ record.status }}
            </a-tag>
          </template>
        </template>
      </a-table>
    </div>

    <!-- Config Panel -->
    <div v-if="selectedNode">
      <a-card :bordered="false">
        <template #title>
          {{ selectedNode.name }} Config
        </template>
        <a-form style="display: flex; flex-direction: column; gap: 12px">
          <div
            v-for="(value, key) in nodeConfig"
            :key="key"
            style="display: flex; flex-direction: column; gap: 4px"
          >
            <label>{{ key }}</label>
            <a-input
              v-model:value="nodeConfig[key]"
              :placeholder="String(value)"
            />
          </div>
        </a-form>
        <a-space style="margin-top: 16px">
          <a-button type="primary" @click="handleSaveConfig">
            Save Config
          </a-button>
          <a-button @click="handleSyncConfig">
            Sync
          </a-button>
        </a-space>
      </a-card>
    </div>
    <div v-else style="grid-column: 2">
      <a-empty description="Select a node to view config" />
    </div>
  </div>
</template>
