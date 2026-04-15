<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { configApi } from '@/api'
import { message } from 'ant-design-vue'

const activeTab = ref('system')
const loading = ref(false)
const config = ref<Record<string, any>>({})
const policy = ref<Record<string, any>>({})

onMounted(async () => {
  await fetchConfig()
})

async function fetchConfig() {
  loading.value = true
  try {
    const [configData, policyData] = await Promise.all([
      configApi.get(),
      configApi.getPolicy(),
    ])

    config.value = configData.config || {}
    policy.value = policyData.policy || {}
  } catch (error) {
    message.error('Failed to load config')
  } finally {
    loading.value = false
  }
}

async function handleSaveConfig() {
  try {
    await configApi.update(config.value)
    message.success('System config saved')
  } catch (error) {
    message.error('Failed to save config')
  }
}

async function handleSavePolicy() {
  try {
    await configApi.updatePolicy(policy.value)
    message.success('Policy saved')
  } catch (error) {
    message.error('Failed to save policy')
  }
}
</script>

<template>
  <a-spin :spinning="loading">
    <a-tabs v-model:activeKey="activeTab">
      <!-- System Config Tab -->
      <a-tab-pane key="system" tab="System Config">
        <a-card :bordered="false">
          <a-form style="display: flex; flex-direction: column; gap: 12px">
            <div
              v-for="(value, key) in config"
              :key="key"
              style="display: flex; flex-direction: column; gap: 4px"
            >
              <label style="font-weight: bold">{{ key }}</label>
              <a-input
                v-model:value="config[key]"
                :placeholder="String(value)"
              />
            </div>
          </a-form>
          <a-button
            type="primary"
            style="margin-top: 16px"
            @click="handleSaveConfig"
          >
            Save Config
          </a-button>
        </a-card>
      </a-tab-pane>

      <!-- Policy Tab -->
      <a-tab-pane key="policy" tab="Policy">
        <a-card :bordered="false">
          <a-form style="display: flex; flex-direction: column; gap: 12px">
            <div
              v-for="(value, key) in policy"
              :key="key"
              style="display: flex; flex-direction: column; gap: 4px"
            >
              <label style="font-weight: bold">{{ key }}</label>
              <a-textarea
                v-model:value="policy[key]"
                :placeholder="String(value)"
                :rows="4"
              />
            </div>
          </a-form>
          <a-button
            type="primary"
            style="margin-top: 16px"
            @click="handleSavePolicy"
          >
            Save Policy
          </a-button>
        </a-card>
      </a-tab-pane>
    </a-tabs>
  </a-spin>
</template>
