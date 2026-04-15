import { defineStore } from 'pinia'
import { ref } from 'vue'
import { agentApi } from '@/api'
import type { Agent } from '@/types'

export const useAgentStore = defineStore('agents', () => {
  const agents = ref<Agent[]>([])
  const currentAgent = ref<Agent | null>(null)
  const loading = ref(false)

  async function fetchAgents(includeSubagents = false) {
    loading.value = true
    try {
      const response = await agentApi.list(includeSubagents)
      agents.value = response.agents
    } catch (error) {
      console.error('Failed to fetch agents:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  function selectAgent(id: string) {
    const agent = agents.value.find((a) => a.id === id)
    if (agent) {
      currentAgent.value = agent
    }
  }

  async function refreshAgent(id: string) {
    try {
      await fetchAgents()
      selectAgent(id)
    } catch (error) {
      console.error('Failed to refresh agent:', error)
      throw error
    }
  }

  return {
    agents,
    currentAgent,
    loading,
    fetchAgents,
    selectAgent,
    refreshAgent,
  }
})
