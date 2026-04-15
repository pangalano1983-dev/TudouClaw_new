<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { mcpApi } from '@/api'
import { message } from 'ant-design-vue'
import type { MCPServer } from '@/types'

const mcpServers = ref<MCPServer[]>([])
const loading = ref(false)

onMounted(async () => {
  await fetchMCPCatalog()
})

async function fetchMCPCatalog() {
  loading.value = true
  try {
    const response = await mcpApi.getCatalog()
    mcpServers.value = response.mcp_servers || []
  } catch (error) {
    message.error('Failed to load MCP catalog')
  } finally {
    loading.value = false
  }
}

async function handleManageMCP(server: MCPServer, action: string) {
  try {
    await mcpApi.manage({ mcp_id: server.id, action })
    message.success(`MCP ${server.name} ${action}ed successfully`)
    await fetchMCPCatalog()
  } catch (error) {
    message.error(`Failed to ${action} MCP`)
  }
}
</script>

<template>
  <div>
    <a-spin :spinning="loading">
      <a-row :gutter="[16, 16]">
        <a-col
          v-for="server in mcpServers"
          :key="server.id"
          :xs="24"
          :sm="12"
          :lg="8"
        >
          <a-card :bordered="false">
            <template #title>
              {{ server.name }}
            </template>
            <div style="display: flex; flex-direction: column; gap: 12px">
              <div>
                <div style="color: #94a3b8; font-size: 12px">Transport</div>
                <div>{{ server.transport }}</div>
              </div>
              <div>
                <div style="color: #94a3b8; font-size: 12px">Scope</div>
                <div>{{ server.scope }}</div>
              </div>
              <div>
                <div style="color: #94a3b8; font-size: 12px">Status</div>
                <a-tag :color="server.enabled ? 'success' : 'default'">
                  {{ server.status }}
                </a-tag>
              </div>
              <a-space>
                <a-button
                  type="primary"
                  size="small"
                  @click="handleManageMCP(server, 'enable')"
                >
                  Enable
                </a-button>
                <a-button
                  size="small"
                  @click="handleManageMCP(server, 'disable')"
                >
                  Disable
                </a-button>
              </a-space>
            </div>
          </a-card>
        </a-col>
      </a-row>
    </a-spin>
  </div>
</template>
