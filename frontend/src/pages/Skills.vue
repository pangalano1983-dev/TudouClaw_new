<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { skillApi } from '@/api'
import { message } from 'ant-design-vue'
import type { SkillPackage } from '@/types'

const skills = ref<SkillPackage[]>([])
const loading = ref(false)
const selectedSkillIds = ref<string[]>([])

const columns = [
  { title: 'Name', dataIndex: 'name', key: 'name', width: 150 },
  { title: 'Description', dataIndex: 'description', key: 'description', width: 200 },
  { title: 'Version', dataIndex: 'version', key: 'version', width: 100 },
  { title: 'Trust Tier', dataIndex: 'trust_tier', key: 'trust_tier', width: 120 },
  { title: 'Status', dataIndex: 'status', key: 'status', width: 100 },
  { title: 'Actions', key: 'actions', width: 150 },
]

onMounted(async () => {
  await fetchSkills()
})

async function fetchSkills() {
  loading.value = true
  try {
    const response = await skillApi.list()
    skills.value = response.skills
  } catch (error) {
    message.error('Failed to load skills')
  } finally {
    loading.value = false
  }
}

async function handleInstall(skill: SkillPackage) {
  try {
    await skillApi.install({ skill_id: skill.id })
    message.success(`Skill ${skill.name} installed`)
    await fetchSkills()
  } catch (error) {
    message.error('Failed to install skill')
  }
}

async function handleGrant(skill: SkillPackage) {
  // In a real app, this would open a modal to select agents
  try {
    await skillApi.grant(skill.id, [])
    message.success(`Skill ${skill.name} granted`)
    await fetchSkills()
  } catch (error) {
    message.error('Failed to grant skill')
  }
}

async function handleRevoke(skill: SkillPackage) {
  // In a real app, this would open a modal to select agents
  try {
    await skillApi.revoke(skill.id, [])
    message.success(`Skill ${skill.name} revoked`)
    await fetchSkills()
  } catch (error) {
    message.error('Failed to revoke skill')
  }
}
</script>

<template>
  <div>
    <a-table
      :columns="columns"
      :data-source="skills"
      :loading="loading"
      :pagination="{ pageSize: 10 }"
      :scroll="{ x: 800 }"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'trust_tier'">
          <a-tag
            :color="
              record.trust_tier === 'high'
                ? 'success'
                : record.trust_tier === 'medium'
                  ? 'warning'
                  : 'error'
            "
          >
            {{ record.trust_tier }}
          </a-tag>
        </template>
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
              @click="handleInstall(record)"
            >
              Install
            </a-button>
            <a-button
              type="link"
              size="small"
              @click="handleGrant(record)"
            >
              Grant
            </a-button>
            <a-button
              type="link"
              size="small"
              danger
              @click="handleRevoke(record)"
            >
              Revoke
            </a-button>
          </a-space>
        </template>
      </template>
    </a-table>
  </div>
</template>
