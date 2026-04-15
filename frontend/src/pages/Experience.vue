<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { experienceApi } from '@/api'
import { message } from 'ant-design-vue'

const stats = ref<any>({
  total_experiences: 0,
  success_count: 0,
  failure_count: 0,
  learning_topics: 0,
})
const experiences = ref<any[]>([])
const loading = ref(false)

const columns = [
  { title: 'Scene', dataIndex: 'scene', key: 'scene', width: 150 },
  { title: 'Type', dataIndex: 'type', key: 'type', width: 100 },
  { title: 'Success Rate', dataIndex: 'success_rate', key: 'success_rate', width: 120 },
  { title: 'Priority', dataIndex: 'priority', key: 'priority', width: 100 },
]

onMounted(async () => {
  await fetchExperienceData()
})

async function fetchExperienceData() {
  loading.value = true
  try {
    const [statsData, listData] = await Promise.all([
      experienceApi.getStats(),
      experienceApi.list(),
    ])

    stats.value = statsData
    experiences.value = listData.experiences || []
  } catch (error) {
    message.error('Failed to load experience data')
  } finally {
    loading.value = false
  }
}

async function handleTriggerRetrospective() {
  try {
    await experienceApi.triggerRetrospective('')
    message.success('Retrospective triggered')
    await fetchExperienceData()
  } catch (error) {
    message.error('Failed to trigger retrospective')
  }
}

async function handleTriggerLearning() {
  try {
    await experienceApi.triggerLearning('', 'general')
    message.success('Learning triggered')
    await fetchExperienceData()
  } catch (error) {
    message.error('Failed to trigger learning')
  }
}
</script>

<template>
  <div>
    <!-- Stats -->
    <a-row :gutter="[16, 16]" style="margin-bottom: 32px">
      <a-col :xs="24" :sm="12" :lg="6">
        <a-card :bordered="false">
          <a-statistic
            title="Total Experiences"
            :value="stats.total_experiences"
          />
        </a-card>
      </a-col>
      <a-col :xs="24" :sm="12" :lg="6">
        <a-card :bordered="false">
          <a-statistic
            title="Successes"
            :value="stats.success_count"
            :value-style="{ color: '#22c55e' }"
          />
        </a-card>
      </a-col>
      <a-col :xs="24" :sm="12" :lg="6">
        <a-card :bordered="false">
          <a-statistic
            title="Failures"
            :value="stats.failure_count"
            :value-style="{ color: '#ef4444' }"
          />
        </a-card>
      </a-col>
      <a-col :xs="24" :sm="12" :lg="6">
        <a-card :bordered="false">
          <a-statistic
            title="Learning Topics"
            :value="stats.learning_topics"
          />
        </a-card>
      </a-col>
    </a-row>

    <!-- Actions -->
    <div style="margin-bottom: 16px">
      <a-space>
        <a-button type="primary" @click="handleTriggerRetrospective">
          Trigger Retrospective
        </a-button>
        <a-button @click="handleTriggerLearning">
          Trigger Learning
        </a-button>
      </a-space>
    </div>

    <!-- Experience Table -->
    <a-table
      :columns="columns"
      :data-source="experiences"
      :loading="loading"
      :pagination="{ pageSize: 10 }"
      :scroll="{ x: 500 }"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'success_rate'">
          <a-progress
            :percent="Math.round(record.success_rate * 100)"
            :status="record.success_rate > 0.8 ? 'success' : 'normal'"
          />
        </template>
        <template v-if="column.key === 'priority'">
          <a-tag
            :color="
              record.priority === 'high'
                ? 'red'
                : record.priority === 'medium'
                  ? 'orange'
                  : 'blue'
            "
          >
            {{ record.priority }}
          </a-tag>
        </template>
      </template>
    </a-table>
  </div>
</template>
