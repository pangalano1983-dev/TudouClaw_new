<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAgentStore } from '@/stores/agents'
import { agentApi } from '@/api'
import { message } from 'ant-design-vue'

const router = useRouter()
const agentStore = useAgentStore()
const loading = ref(false)
const stats = ref({
  total_agents: 0,
  active_agents: 0,
  total_projects: 0,
  total_workflows: 0,
})

onMounted(async () => {
  await fetchDashboardData()
})

async function fetchDashboardData() {
  loading.value = true
  try {
    await agentStore.fetchAgents()
    stats.value.total_agents = agentStore.agents.length
    stats.value.active_agents = agentStore.agents.filter((a) => a.status !== 'offline').length
    stats.value.total_projects = 0
    stats.value.total_workflows = 0
  } catch (error) {
    message.error('Failed to load dashboard data')
  } finally {
    loading.value = false
  }
}

function handleAgentClick(id: string) {
  router.push({ name: 'AgentChat', params: { id } })
}
</script>

<template>
  <div>
    <!-- Stat Cards -->
    <a-row :gutter="[16, 16]" style="margin-bottom: 32px">
      <a-col :xs="24" :sm="12" :lg="6">
        <a-card :bordered="false">
          <a-statistic
            title="Total Agents"
            :value="stats.total_agents"
          />
        </a-card>
      </a-col>
      <a-col :xs="24" :sm="12" :lg="6">
        <a-card :bordered="false">
          <a-statistic
            title="Active"
            :value="stats.active_agents"
            :value-style="{ color: '#22c55e' }"
          />
        </a-card>
      </a-col>
      <a-col :xs="24" :sm="12" :lg="6">
        <a-card :bordered="false">
          <a-statistic
            title="Projects"
            :value="stats.total_projects"
          />
        </a-card>
      </a-col>
      <a-col :xs="24" :sm="12" :lg="6">
        <a-card :bordered="false">
          <a-statistic
            title="Workflows"
            :value="stats.total_workflows"
          />
        </a-card>
      </a-col>
    </a-row>

    <!-- Agents Grid -->
    <div style="margin-bottom: 16px">
      <h2>Active Agents</h2>
    </div>
    <a-spin :spinning="loading">
      <a-row :gutter="[16, 16]">
        <a-col
          v-for="agent in agentStore.agents"
          :key="agent.id"
          :xs="24"
          :sm="12"
          :lg="8"
        >
          <a-card
            :bordered="false"
            style="cursor: pointer; transition: transform 0.2s"
            @click="handleAgentClick(agent.id)"
            @mouseenter="(e) => (e.currentTarget as HTMLElement).style.transform = 'translateY(-4px)'"
            @mouseleave="(e) => (e.currentTarget as HTMLElement).style.transform = 'translateY(0)'"
          >
            <div style="display: flex; align-items: center; margin-bottom: 12px">
              <div style="font-size: 32px; margin-right: 12px">
                {{ agent.robot_avatar }}
              </div>
              <div>
                <h3 style="margin: 0">{{ agent.name }}</h3>
                <p style="margin: 0; color: #94a3b8">{{ agent.role }}</p>
              </div>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center">
              <a-tag
                :color="
                  agent.status === 'idle'
                    ? 'success'
                    : agent.status === 'busy'
                      ? 'processing'
                      : 'error'
                "
              >
                {{ agent.status }}
              </a-tag>
              <span style="color: #94a3b8; font-size: 12px">{{ agent.model }}</span>
            </div>
          </a-card>
        </a-col>
      </a-row>
    </a-spin>
  </div>
</template>
